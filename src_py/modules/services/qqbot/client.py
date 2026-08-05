import asyncio
import json
import time
from typing import Any, Dict,Optional
import httpx
from websockets import connect,ClientConnection
from websockets.exceptions import ConnectionClosed

from ...tools.models import ToolFunction, ToolFunctionParameters
from ...events.data import BaseEvent
from ...logger import logger
from ..config import QQBotConfig
from .. import base
from . import models
from ...events import emit, types as eventType, on_event_class
from ...manager.service.decorator import Service
from .. import ServiceId

# QQ Bot API 端点
TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
GATEWAY_URL = "https://api.sgroup.qq.com/gateway"  # 正式环境，沙箱用 sandbox.api.sgroup.qq.com/gateway
@on_event_class([
    (eventType.QQBotEventType.QQ_BOT_START, "start"),
    (eventType.QQBotEventType.QQ_BOT_STOP, "stop"),
    (eventType.QQBotEventType.QQ_BOT_INFO, "get_bot_info")
])
@Service(id=ServiceId.QQBOT)
class QQBotClient(base._BaseService):
    """
        Reference:
            <a href="https://bot.q.qq.com/wiki/develop/api-v2/#">QQ Bot API V2</a>
        Parameters:
            appid: QQ Bot应用ID
            secret: QQ Bot应用密钥
    """
    name="QQBot"
    description="用于控制QQ Bot服务"

    def __init__(self,appid: str, secret: str, debug: bool = False, **kwargs):
        super().__init__()
        self.config=QQBotConfig(enabled=True,appid=appid, secret=secret, **kwargs)
        self.debug = debug
        self.__token: Optional[str] = None
        self.__token_expire: float = 0.0
        self.__ws: Optional[ClientConnection] = None
        self.__session: Optional[httpx.AsyncClient] = None
        self.__seq: Optional[int] = None
        self.__session_id: Optional[str] = None
        self.__running: bool = False
        self.__heartbeat_task: Optional[asyncio.Task] = None
        self.__lifecycle_handlers = {
            models.QQBotEvent.LifecycleEvent.GUILD_CREATE: self.__on_guild_created, # 群创建
            models.QQBotEvent.LifecycleEvent.GUILD_DELETE: self.__on_guild_deleted, # 群删除
            models.QQBotEvent.LifecycleEvent.GUILD_UPDATE: self.__on_guild_updated, # 群更新
            models.QQBotEvent.LifecycleEvent.CHANNEL_CREATE: self.__on_channel_created, # 渠道创建
            models.QQBotEvent.LifecycleEvent.CHANNEL_DELETE: self.__on_channel_deleted, # 渠道删除
            models.QQBotEvent.LifecycleEvent.CHANNEL_UPDATE: self.__on_channel_updated, # 渠道更新
            models.QQBotEvent.LifecycleEvent.GROUP_ADD_ROBOT: self.__on_group_added, # 机器人被添加到群
            models.QQBotEvent.LifecycleEvent.GROUP_DEL_ROBOT: self.__on_group_removed,  # 机器人被踢出群
            models.QQBotEvent.LifecycleEvent.GROUP_MSG_REJECT: self.__on_group_msg_rejected,  # 机器人被禁言
            models.QQBotEvent.LifecycleEvent.FRIEND_ADD: self.__on_friend_added, # 好友添加
            models.QQBotEvent.LifecycleEvent.FRIEND_DEL: self.__on_friend_deleted, # 好友删除
            models.QQBotEvent.LifecycleEvent.C2C_MSG_CREATE: self.__on_c2c_msg_created,  # 2C消息创建
            models.QQBotEvent.LifecycleEvent.C2C_MSG_REJECT: self.__on_c2c_msg_rejected, # 2C消息被拒绝
            models.QQBotEvent.LifecycleEvent.DIRECT_MESSAGE_CREATE: self.__on_direct_message, # 直接消息创建
            models.QQBotEvent.LifecycleEvent.INTERACTION_CREATE: self.__on_interaction_create, # 互动创建
        }
        self.set_status()
        self.bot_info: Optional[models.QQBotData.QQBotInfo] = None
    
    #控制工具命令
    def get_tools(self) -> base.ServiceTool:
        return [
            ToolFunction(
                name="send_message",
                description="发送消息",
                parameters=ToolFunctionParameters(
                    type="object",
                    properties={
                        "guild_id": {"type": "string", "description": "群ID"},
                        "channel_id": {"type": "string", "description": "渠道ID"},
                        "message": {"type": "string", "description": "要发送的消息"},
                    },
                    required=["guild_id", "channel_id", "message"]
                )
            ),
            ToolFunction(
                name="get_bot_info",
                description="获取机器人信息",
                parameters=ToolFunctionParameters(
                    type="object",
                    properties={
                        "guild_id": {
                            "type": "string", 
                            "description": "群ID"
                        },
                    },
                    required=["guild_id"]
                )
            ),
        ]
    
    def set_status(self):
        if self.__running:
            self.status= base.ServiceState.RUNNING
        else:
            self.status= base.ServiceState.STOPPED
    
    async def start(self):
        self.__running = True
        self.set_status()
        self.__session = httpx.AsyncClient(timeout=30.0)
        await self.__ensure_token()
        asyncio.create_task(self.__connect_gateway())
        #初始化获取一次机器人信息
        self.bot_info = await self.get_bot_info()
        logger.info(f"[QQBot] Bot info: {self.bot_info}")
        emit(BaseEvent(type=eventType.QQBotEventType.QQ_BOT_INFO, args=(self.bot_info,)))
    
    async def stop(self):
        self.__running = False
        if self.__heartbeat_task:
            self.__heartbeat_task.cancel()
        if self.__ws is not None and not hasattr(self.__ws, "close_code"):
            await self.__ws.close() # type: ignore
        if self.__session:
            await self.__session.aclose()
        logger.info("[QQBot] Service closed")
        self.set_status()

    # =========================================================
    # 鉴权与Token管理
    # =========================================================
    async def __ensure_token(self):
        """
            获取或刷新 AccessToken `POST app/getAppAccessToken`

            参数
                ```json
                {
                    "appId": "your_app_id",
                    "clientSecret": "your_client_secret"
                }
                ``````

            返回结果
                ```json
                {
                    "access_token": "your_access_token",
                    "expires_in": 7200
                }
                ```
        """
        if self.__session is None:
            raise ValueError("ClientSession not initialized")
        now = time.time()
        # 提前60秒刷新
        if self.__token and now < self.__token_expire - 60:
            return
        
        logger.info("[QQBot] Fetching new access_token...")
        if not self.config:
            raise ValueError("Config not initialized")
        payload = {
            "appId": self.config.appid,
            "clientSecret": self.config.secret
        }
        resp = await self.__session.post(TOKEN_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"[QQBot] Token response: {data}")
        self.__token = data["access_token"]
        self.__token_expire = now + float(data.get("expires_in", 7200))
        logger.info(f"[QQBot] Fetched new access_token: {self.__token} with expire time: {self.__token_expire}")


    def __headers(self) -> Dict:
        """构造API请求头"""
        if not self.config:
            raise ValueError("Config not initialized")
        return {
            "Authorization": f"QQBot {self.__token}",
            "Content-Type": "application/json",
            "X-Union-Appid": self.config.appid
        }

    # =========================================================
    # WebSocket Gateway 连接与维护
    # =========================================================
    async def __get_websocket_url(self) -> str:
        """
        从gateway接口获取WebSocket地址 `GET /gateway`
        
        ```json
        {
            "url": "wss://api.sgroup.qq.com/websocket/",
        }
        ```
        """
        if self.__session is None:
            raise ValueError("ClientSession not initialized")
            
        url = GATEWAY_URL
        if not self.config:
            raise ValueError("Config not initialized")

        if self.config.sandbox:
            url = "https://sandbox.api.sgroup.qq.com/gateway"
        
        headers = {"Authorization": f"QQBot {self.__token}"}
        logger.info(f"[QQBot] Requesting websocket URL from {url} with headers: {headers}")
        response = await self.__session.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        logger.info(f"[QQBot] Gateway response: {data}")
        ws_url = data.get("url")
        if not ws_url:
            raise ValueError(f"Failed to get websocket URL from gateway: {data}")
        logger.info(f"[QQBot] Got websocket URL: {ws_url}")
        return ws_url

    async def __connect_gateway(self):
        """
        连接WebSocket Gateway `WS`

        response:
        ```json
        {
            "id": "...",
            "op": 10,
            "d": { ... },
            "t": "EVENT_TYPE",
            "s": 0
        }
        `
        """
        if self.__session is None:
            return
        # 1. 获取Gateway地址（先获取WebSocket URL）
        ws_url = await self.__get_websocket_url()        
        # 2. 建立WS连接
        headers = {"Authorization": f"QQBot {self.__token}"}
        while self.__running:
            try:
                async with connect(
                    ws_url,
                    extra_headers=headers,
                    ping_interval=None,  # 自己管理心跳
                    max_size=None
                ) as ws:
                    self.__ws = ws
                    logger.info("[QQBot] WebSocket connected")
                    async for msg in ws:
                        if msg:
                            payload = json.loads(msg)
                            await self.__handle_payload(payload)
            except (ConnectionClosed, asyncio.CancelledError):
                logger.info("[QQBot] WebSocket connection closed")
            except Exception as e:
                logger.error(f"[QQBot] WS connection error: {e}, reconnecting in 5s...")
                await asyncio.sleep(5)
            finally:
                await self.stop()

    async def __handle_payload(self, payload: Dict):
        if not payload or not self.__ws:
            return
        print("[QQBot] Received payload: {payload}")
        logger.info(f"[QQBot] Received payload: {payload}")
        op = payload.get("op")
        d = payload.get("d")
        t = payload.get("t", "")
        s = payload.get("s")
        if op is None or not isinstance(op,int):
            return
        resp = models.QQBotData.QQBotResponse(
            opCode=op,
            seq=int(s) if s is not None else None,
            type=str(t),
            data=d or {}
        )

        if resp.seq is not None:
            self.__seq = resp.seq

        # OpCode 10 Hello (下发心跳间隔)
        if op == models.QQBotEvent.WebSocketEvent.HEARTBEAT:
            interval = resp.data.get("heartbeat_interval", 30000) # type:ignore
            self.__heartbeat_task = asyncio.create_task(self.__heartbeat(interval))
            await self.__send_identify()
        
        # OpCode 0 Dispatch (事件分发)
        elif op == models.QQBotEvent.WebSocketEvent.DISPATCH:
            logger.debug(f"[QQBot] Event: {resp.type}, Data: {resp.data}")
            await self.__dispatch_event(resp.type, resp.data)
        
        # OpCode 7 Reconnect
        elif op == models.QQBotEvent.WebSocketEvent.RECONNECT:
            logger.warning("[QQBot] Server requested reconnect")
            await self.__ws.close()
        
        # OpCode 9 Invalid Session
        elif op == models.QQBotEvent.WebSocketEvent.INVALID_SESSION:
            logger.error("[QQBot] Invalid session, re-identifying...")
            await asyncio.sleep(1)
            await self.__send_identify()

    async def __send_identify(self):
        if not self.__ws:
            return
        """发送鉴权包 (OpCode 2)"""
        if not self.config:
            raise ValueError("Config not initialized")
        payload = {
            "op": 2,
            "d": {
                "token": f"QQBot {self.__token}",
                "intents": self.config.intents,
                "shard": self.config.shard,
                "properties": {
                    "$os": "linux",
                    "$language": "python",
                    "client": "custom_sdk"
                }
            }
        }
        if self.__session_id:
            payload["d"]["session_id"] = self.__session_id
        
        await self.__ws.send(json.dumps(payload))
    
    # =========================================================
    # 事件分发
    # =========================================================
    async def __dispatch_event(self, event_type: str, data: Dict):
        """
        可用事件名：

        - on_bot_deleted: 机器人被删除
        - on_bot_kicked: 机器人被踢出群
        - on_group_added: 机器人加入新群
        - on_group_removed: 机器人退出群
        - on_friend_added: 机器人被添加好友
        - on_friend_removed: 机器人被删除好友
        - on_guild_joined: 机器人加入频道
        - on_guild_left: 机器人离开频道
        - on_disconnected: 连接断开
        - on_reconnected: 重新连接成功
        - on_session_invalid: Session失效
        """
        """分发QQ事件，处理生命周期事件"""
        
        # 记录session_id（Ready事件时获取）
        if event_type == "READY":
            self._session_id = data.get("session_id")
            version = data.get("version")
            logger.info(f"[QQBot] Ready - SessionID: {self._session_id}, Version: {version}")
            return
            
        handler = self.__lifecycle_handlers.get(event_type)
        if handler:
            handler(data)
    
    def __on_c2c_msg_created(self, data: Dict):
        """2C消息创建"""
        content = data.get("content")
        user_id = data.get("author", {}).get("user_openid")
        if content is None or user_id is None:
            return
        self.__trigger_lifecycle(eventType.QQBotEventType.QQ_BOT_C2C_MSG_CREATE, {
            "content": content,
            "user_id": user_id
        })

    async def __heartbeat(self, interval_ms: int):
        while self.__running and self.__ws:
            try:
                payload = {"op": 1, "d": self.__seq}
                await self.__ws.send(json.dumps(payload))
                logger.debug("[QQBot] Heartbeat sent")
            #取消
            except asyncio.CancelledError:
                logger.info("[QQBot] Heartbeat cancelled")
                break
            except Exception as e:
                logger.error(f"[QQBot] Heartbeat failed: {e}")
                break
            await asyncio.sleep(interval_ms / 1000)

    # =========================================================
    # REST API 封装
    # =========================================================
    async def send_group_message(
        self,
        group_openid: str,
        content: str,
        msg_id: Optional[str] = None,
        msg_type: int = 0
    ) -> Dict:
        """
            发送群消息 `POST /v2/groups/{group_openid}/messages`
        """
        if self.__session is None:
            raise Exception("QQBot session not initialized")
        await self.__ensure_token()
        url = f"https://api.sgroup.qq.com/v2/groups/{group_openid}/messages"
        if not self.config:
            raise ValueError("Config not initialized")
        if self.config.sandbox:
            url = f"https://sandbox.api.sgroup.qq.com/v2/groups/{group_openid}/messages"
        
        payload = {
            "content": content,
            "msg_type": msg_type
        }
        if msg_id:
            payload["msg_id"] = msg_id
        resp=await self.__session.post(url, json=payload, headers=self.__headers())
        data = resp.json()
        if resp.status_code != 200:
            logger.error(f"[QQBot] Send group msg failed: {data}")
        return data

    async def send_user_message(
        self,
        user_openid: str,
        content: str,
        msg_type: int = models.QQBotEvent.MessageType.TEXT,
        file_info: Optional[Any] = None,
        msg_id: Optional[str] = None
    ) -> Dict:
        """
            发送单聊(C2C)消息 `POST /v2/users/{user_openid}/messages`
        """
        if self.__session is None:
            raise Exception("QQBot session not initialized")
        await self.__ensure_token()
        url = f"https://api.sgroup.qq.com/v2/users/{user_openid}/messages"
        if not self.config:
            raise ValueError("Config not initialized")
        if self.config.sandbox:
            url = f"https://sandbox.api.sgroup.qq.com/v2/users/{user_openid}/messages"
        
        payload = {
            "content": content,
            "msg_type": msg_type
        }
        if msg_id:
            payload["msg_id"] = msg_id
        resp = await self.__session.post(url, json=payload, headers=self.__headers())
        if resp.status_code != 200:
            logger.error(f"[QQBot] Send user msg failed: {resp.status_code}")
        data = resp.json()
        return data

    async def get_bot_info(self) -> models.QQBotData.QQBotInfo:
        """
            获取机器人自身信息 `GET /v2/users/@me`
        """
        if self.__session is None:
            raise Exception("QQBot session not initialized")
        if self.bot_info is not None:
            return self.bot_info #避免多次调用接口
        await self.__ensure_token()
        url = "https://api.sgroup.qq.com/users/@me"
        response = await self.__session.get(url, headers=self.__headers())
        if response.status_code != 200:
            logger.error(f"[QQBot] Get self info failed: {response.status_code}")
        data = response.json()
        return data

    # =========================================================
    # 辅助方法
    # =========================================================
    def get_info(self) -> Dict:
        """重写基类方法，返回服务状态"""
        if not self.config:
            raise ValueError("Config not initialized")
        return {
            "name": self.name,
            "appid": self.config.appid,
            "connected": self.__ws is not None and not hasattr(self.__ws, "close_code"),
            "seq": self.__seq
        }
    

    # =========================================================
    # 生命周期事件处理
    # =========================================================
    def __on_guild_created(self, data: Dict):
        """机器人加入新频道"""
        guild_id = data.get("id", "unknown")
        guild_name = data.get("name", "unknown")
        logger.info(f"[QQBot] Bot joined guild - ID: {guild_id}, Name: {guild_name}")
        
        self.__trigger_lifecycle("on_guild_joined", {
            "guild_id": guild_id,
            "guild_name": guild_name,
            "data": data
        })

    def __on_guild_deleted(self, data: Dict):
        """ 机器人被移出频道（被踢/解散）
          请求参数
          ```json
          {
            "id": "guild_id",
            "name": "guild_name",
            "op_user_id": "operator_id"
          }
          ```
        """
        guild_id = data.get("id", "unknown")
        guild_name = data.get("name", "unknown")
        operator_id = data.get("op_user_id", "unknown")
        
        logger.warning(f"[QQBot] ⚠️ Bot was removed from guild - ID: {guild_id}, Name: {guild_name}, Operator: {operator_id}")
        
        self.__trigger_lifecycle("on_bot_kicked", {
            "guild_id": guild_id,
            "guild_name": guild_name,
            "operator_id": operator_id,
            "reason": "removed_from_guild",
            "data": data
        })

    async def __on_guild_updated(self, data: Dict):
        """频道信息更新"""
        guild_id = data.get("id", "unknown")
        logger.info(f"[QQBot] Guild updated - ID: {guild_id}")

    async def __on_channel_created(self, data: Dict):
        """子频道创建"""
        channel_id = data.get("id", "unknown")
        channel_name = data.get("name", "unknown")
        logger.info(f"[QQBot] Channel created - ID: {channel_id}, Name: {channel_name}")

    def __on_channel_deleted(self, data: Dict):
        """子频道删除"""
        channel_id = data.get("id", "unknown")
        channel_name = data.get("name", "unknown")
        logger.info(f"[QQBot] Channel deleted - ID: {channel_id}, Name: {channel_name}")

    def __on_channel_updated(self, data: Dict):
        """子频道更新"""
        channel_id = data.get("id", "unknown")
        logger.info(f"[QQBot] Channel updated - ID: {channel_id}")

    def __on_group_added(self, data: Dict):
        """机器人被添加到群聊"""
        group_openid = data.get("group_openid", "unknown")
        timestamp = data.get("timestamp", 0)
        logger.info(f"[QQBot] ✅ Bot added to group - GroupOpenID: {group_openid}")
        
        self.__trigger_lifecycle(eventType.QQBotEventType.QQ_BOT_ON_GROUP_ADDED, {
            "group_openid": group_openid,
            "timestamp": timestamp,
            "data": data
        })

    def __on_group_removed(self, data: Dict):
        """
        机器人被踢出群聊或被群管理员删除
        """
        group_openid = data.get("group_openid", "unknown")
        op_member_openid = data.get("op_member_openid", "unknown")
        timestamp = data.get("timestamp", 0)
        
        logger.warning(f"[QQBot] ❌ Bot was kicked from group!")
        logger.warning(f"[QQBot]    GroupOpenID: {group_openid}")
        logger.warning(f"[QQBot]    Operator: {op_member_openid}")
        logger.warning(f"[QQBot]    Timestamp: {timestamp}")
        self.__log_bot_event("kicked_from_group", {
            "group_openid": group_openid,
            "operator": op_member_openid,
            "timestamp": timestamp
        })
        self.__trigger_lifecycle("on_bot_kicked", {
            "group_openid": group_openid,
            "operator_id": op_member_openid,
            "reason": "kicked_from_group",
            "timestamp": timestamp,
            "data": data
        })
    

    def __on_group_msg_rejected(self, data: Dict):
        """机器人被群禁言"""
        group_openid = data.get("group_openid", "unknown")
        logger.warning(f"[QQBot] 🔇 Bot muted in group - GroupOpenID: {group_openid}")
        
        self.__log_bot_event("muted_in_group", {
            "group_openid": group_openid,
            "timestamp": data.get("timestamp", 0)
        })

    def __on_friend_added(self, data: Dict):
        """机器人被添加好友"""
        user_openid = data.get("openid", "unknown")
        logger.info(f"[QQBot] 🤝 Friend added - UserOpenID: {user_openid}")
        self.__trigger_lifecycle(eventType.QQBotEventType.QQ_BOT_ON_FRIEND_ADDED, {
            "user_openid": user_openid,
            "data": data
        })

    def __on_friend_deleted(self, data: Dict):
        """机器人被删除好友"""
        user_openid = data.get("openid", "unknown")
        logger.warning(f"[QQBot] 👋 Friend removed - UserOpenID: {user_openid}")
        self.__trigger_lifecycle("on_friend_removed", {
            "user_openid": user_openid,
            "data": data
        })

    def __on_c2c_msg_rejected(self, data: Dict):
        """用户拒绝接收机器人消息"""
        user_openid = data.get("openid", "unknown")
        logger.warning(f"[QQBot] 🚫 C2C message rejected by user - UserOpenID: {user_openid}")

    def __on_direct_message(self, data: Dict):
        """收到私信消息"""
        author = data.get("author", {})
        user_openid = author.get("id", "unknown")
        logger.info(f"[QQBot] Direct message from user: {user_openid}")

    def __on_interaction_create(self, data: Dict):
        """交互事件（按钮点击等）"""
        interaction_id = data.get("id", "unknown")
        logger.info(f"[QQBot] Interaction created - ID: {interaction_id}")

    # =========================================================
    # 日志记录与通知
    # =========================================================
    def __log_bot_event(self, event_type: str, details: Dict):
        """
        记录机器人生命周期事件到持久化日志
        可用于后续分析或监控
        """
        if not self.config:
            return
        log_entry = {
            "event": event_type,
            "appid": self.config.appid,
            "timestamp": time.time(),
            "details": details
        }
        # 记录到logger
        logger.info(f"[QQBot-LOG] Bot event: {json.dumps(log_entry, ensure_ascii=False)}")
        

    def __trigger_lifecycle(self, event_name: str, data: Dict):
        if not self.debug:
            return
        from ...events import emit
        emit(BaseEvent(type=event_name, args=(data,)))
