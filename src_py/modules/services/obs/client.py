from __future__ import annotations
import asyncio
import base64
import hashlib
import threading
from json import JSONDecodeError, dumps, loads
from typing import Any, Dict, List, Optional

from ...events import on_event_class, types as eventType
from ...logger import logger
from ...manager.service.decorator import Service
from ...pipeline.models import ToolFunction, ToolFunctionParameters
from ...utils import util
from ..keys import ServiceKeys
from ..base import BaseService, ServiceState
from ..config import ObsConfig
from . import models

# 断线重连退避（秒）
RECONNECT_BASE_DELAY = 1.0
RECONNECT_MAX_DELAY = 15.0


@on_event_class([
    (eventType.ObsEventType.OBS_CONNECT, "start"),
    (eventType.ObsEventType.OBS_DISCONNECT, "stop"),
    # S29：录音开关绑到录音方法，不再绑到 ASR 音频处理
    (eventType.ObsEventType.OBS_START_RECORD, "start_record"),
    (eventType.ObsEventType.OBS_STOP_RECORD, "stop_record"),
])
@Service(id=ServiceKeys.OBS)
class OBSClient(BaseService):
    """控制 OBS Studio（录制 / 直播 / 场景切换等）。

    References:
        https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md

    Parameters:
        ip: OBS 服务器 IP
        obs_password: OBS WebSocket 密码
        port: 端口，默认 4455
        timeout: 连接超时
    """

    name = "OBS"
    description = "用于控制OBS Studio录制等服务"

    def __init__(
        self,
        ip: str = "127.0.0.1",
        obs_password: str = "",
        port: int = 4455,
        timeout: int = 10
    ):
        super().__init__()
        self.config = ObsConfig(
            enabled=True,
            ip=ip,
            password=obs_password,
            port=port,
        )  # type: ignore[union-attr]
        self.timeout = timeout
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._event_callbacks: Dict[str, list] = {}  # eventType -> [callbacks]
        self._negotiated_rpc_version: Optional[int] = None
        self.__runing: bool = False
        self.__ws: Optional[Any] = None
        self.__loop: Optional[asyncio.AbstractEventLoop] = None
        self.__thread: Optional[threading.Thread] = None
        self.set_status()

    # ---------- 状态 ----------

    def set_status(self) -> None:
        """S27：走基类，统一写 `state`。"""
        super().set_status(ServiceState.RUNNING if self.__runing else ServiceState.STOPPED)

    @property
    def is_connected(self) -> bool:
        """S25：`closed` 取的是值，不是 hasattr。"""
        ws = self.__ws
        if ws is None:
            return False
        closed = getattr(ws, "closed", None)
        if closed is None:
            return True
        return not bool(closed)

    # ---------- 生命周期 ----------

    async def start(self) -> None:
        if self.__runing:
            return
        self.__runing = True
        self.set_status()
        # S28：在有运行中 loop 的线程里直接起任务
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self.__start_loop_thread()
        else:
            asyncio.create_task(self.connect())

    def __start_loop_thread(self) -> None:
        """S28：无运行中 loop 时（如主线程 / 服务线程）自建 loop 线程。

        OBS 客户端是纯 async 服务，不能要求调用方一定在协程上下文里。
        """
        if self.__thread is not None and self.__thread.is_alive():
            return

        ready = threading.Event()

        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.__loop = loop
            ready.set()
            try:
                loop.run_until_complete(self.connect())
            finally:
                try:
                    loop.run_until_complete(loop.shutdown_asyncgens())
                except Exception:
                    pass
                loop.close()
                self.__loop = None

        self.__thread = threading.Thread(target=_run, name="OBSClient", daemon=True)
        self.__thread.start()
        ready.wait(timeout=5.0)

    async def connect(self) -> None:
        """连接并维持长连接；断线后按退避重连（S31）。"""
        if self.__ws is not None:
            return

        delay = RECONNECT_BASE_DELAY
        try:
            from websockets import connect
            from websockets.exceptions import ConnectionClosed
            from websockets.typing import Subprotocol
        except ImportError as e:  # pragma: no cover
            logger.error(f"[OBS] 缺少 websockets 依赖: {e}")
            self.__runing = False
            self.set_status()
            return

        ws_url = f"ws://{self.config.ip}:{self.config.port}"  # type: ignore[union-attr]
        try:
            while self.__runing:
                try:
                    async with connect(
                        ws_url,
                        subprotocols=[Subprotocol("obswebsocket.json")],
                        open_timeout=self.timeout,
                    ) as ws:
                        self.__ws = ws
                        delay = RECONNECT_BASE_DELAY  # 连上了就重置退避
                        logger.info(f"[OBS] 已连接 {ws_url}")
                        async for msg in ws:
                            try:
                                data = loads(msg)
                            except JSONDecodeError:
                                continue
                            await self.__handle_event(models.OBSResponseData(
                                status_code=data.get("op"),
                                data=data.get("d"),
                            ))
                except ConnectionClosed:
                    logger.warning("[OBS] 连接已关闭")
                except ConnectionRefusedError:
                    logger.error("[OBS] 连接被拒绝，请确认已启动 OBS WebSocket 服务器")
                except Exception as e:
                    logger.exception(f"[OBS] 连接异常: {e}", exc_info=True)

                # S26：无论怎么退出的，都把 ws 引用清掉，保证可重连
                self.__ws = None

                if not self.__runing:
                    break
                logger.info(f"[OBS] {delay:.1f}s 后重连")
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX_DELAY)
        finally:
            # S28：只有真正退出循环才标记停止
            if self.__runing:
                await self.stop()

    async def stop(self) -> None:
        self.__runing = False
        ws = self.__ws
        # S26：先置空再关闭，避免重连时 connect() 直接 return
        self.__ws = None
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass
        # 未完成的请求不能让调用方永久挂起
        for fut in list(self._pending_requests.values()):
            if not fut.done():
                fut.cancel()
        self._pending_requests.clear()
        self.set_status()

    async def close(self) -> None:
        await self.stop()

    # ---------- 协议 ----------

    async def _send(self, request: dict) -> None:
        if self.__ws is None:
            raise ConnectionError("OBS客户端未连接")
        await self.__ws.send(dumps(request))

    def __build_identify(self, d: dict, auth_string: Optional[str] = None) -> dict:
        rpc_version = d.get("rpcVersion", 1)
        payload: dict = {
            "rpcVersion": rpc_version,
            "eventSubscriptions": models.OBSEventType.EventSubscription.ALL,
        }
        if auth_string is not None:
            payload["authentication"] = auth_string
        return {"op": 1, "d": payload}

    async def __handle_event(self, response: models.OBSResponseData) -> None:
        op = response.status_code
        data = response.data or {}

        if op == models.OBSEventType.ObsWebsocketSERIVE.SERVICE_CONNECT:  # 0 Hello
            await self.__auth(response)
            return

        if op == models.OBSEventType.ObsWebsocketSERIVE.SERVICE_RECOGNIZED_SUCCESS:  # 2
            self._negotiated_rpc_version = data.get("negotiatedRpcVersion")
            return

        if op == models.OBSEventType.ObsWebsocketSERIVE.SERVICE_EVENT_RESULT:  # 5 Event
            event_type = data.get("eventType","")
            event_data = data.get("eventData") or {}
            for callback in self._event_callbacks.get(event_type, []):
                try:
                    result = callback(event_data)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    logger.debug(f"[OBS] event callback failed: {event_type}")
            return

        if op == models.OBSEventType.ObsWebsocketSERIVE.SERVICE_REQUEST_RESPONSE:  # 7
            # S24：这里原来用的是 SERVICE_EVENT_RESULT(5)，分支永不进入
            request_id = data.get("requestId","")
            fut = self._pending_requests.pop(request_id, None)
            if fut is not None and not fut.done():
                fut.set_result({
                    "requestStatus": data.get("requestStatus"),
                    "responseData": data.get("responseData"),
                })

    def on_event(self, event_type: str, callback) -> None:
        """订阅 OBS 事件（如 `CurrentProgramSceneChanged`）。"""
        self._event_callbacks.setdefault(event_type, []).append(callback)

    async def request(
        self,
        request_type: str,
        request_data: Optional[dict] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """发送请求并等待响应，返回 responseData；失败时抛 OBSRequestError。"""
        loop = asyncio.get_running_loop()
        request_id = util.id_generator()
        fut: asyncio.Future = loop.create_future()
        self._pending_requests[request_id] = fut

        req = models.OBSRequestParams(
            op=models.OBSEventType.ObsWebsocketCLINETEvent.CLIENT_GET_EVENT,
            d={
                "requestType": request_type,
                "requestId": request_id,
                "requestData": request_data or {},
            },
        )
        await self._send(req.__dict__)
        try:
            result = await asyncio.wait_for(fut, timeout=timeout or self.timeout)
        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            raise

        status = result.get("requestStatus") or {}
        if not status.get("result", False):
            raise models.OBSError.RequestError(
                status.get("code", -1),
                status.get("comment"),
                result,
            )
        return result.get("responseData") or {}

    async def __auth(self, response: models.OBSResponseData) -> None:
        auth_obj = (response.data or {}).get("authentication")
        if not auth_obj:
            await self._send(self.__build_identify(response.data or {}))
            return
        challenge: str = auth_obj.get("challenge", "")
        salt: str = auth_obj.get("salt", "")
        if not self.config:
            return
        sha256_secret = self.__generate_base64_secret(self.config.password + salt)
        my_auth = self.__generate_base64_secret(sha256_secret + challenge)
        await self._send(self.__build_identify(response.data or {}, my_auth))

    @staticmethod
    def __generate_base64_secret(secret: str) -> str:
        return base64.b64encode(
            hashlib.sha256(secret.encode()).digest()
        ).decode("utf-8")

    # ---------- General ----------

    async def get_version(self) -> dict:
        return await self.request(models.OBSEventType.GeneralEventType.VERSION)

    async def get_stats(self) -> dict:
        return await self.request(models.OBSEventType.GeneralEventType.STATS)

    async def get_hotkey_list(self) -> dict:
        return await self.request(models.OBSEventType.GeneralEventType.HOTKEY_LIST)

    # ---------- Config ----------

    async def get_scene_collection_list(self) -> dict:
        return await self.request(models.OBSEventType.ConfigEventType.SCENE_COLLECTION_LIST)

    async def set_current_scene_collection(self, scene_collection_name: str) -> None:
        await self.request(
            models.OBSEventType.ConfigEventType.SET_CURRENT_SCENE_COLLECTION,
            {"sceneCollectionName": scene_collection_name},
        )

    async def get_profile_list(self) -> dict:
        return await self.request(models.OBSEventType.ConfigEventType.PROFILE_LIST)

    async def get_video_settings(self) -> dict:
        return await self.request(models.OBSEventType.ConfigEventType.GET_VIDEO_SETTINGS)

    async def set_video_settings(self, **kwargs: Any) -> None:
        await self.request(models.OBSEventType.ConfigEventType.SET_VIDEO_SETTINGS, kwargs)

    async def get_record_directory(self) -> dict:
        return await self.request(models.OBSEventType.ConfigEventType.GET_RECORD_DIRECTORY)

    async def set_record_directory(self, record_directory: str) -> None:
        await self.request(
            models.OBSEventType.ConfigEventType.SET_RECORD_DIRECTORY,
            {"recordDirectory": record_directory},
        )

    # ---------- Scenes ----------

    async def get_scene_list(self) -> dict:
        return await self.request(models.OBSEventType.SceneEventType.GET_SCENE_LIST)

    async def get_current_program_scene(self) -> dict:
        return await self.request(models.OBSEventType.SceneEventType.GET_CURRENT_PROGRAM_SCENE)

    async def set_current_program_scene(self, scene_name: str) -> None:
        await self.request(
            models.OBSEventType.SceneEventType.SET_CURRENT_PROGRAM_SCENE,
            {"sceneName": scene_name},
        )

    async def switch_scene(self, scene_name: str) -> None:
        """切换场景（命令文档里的名字，语义同 set_current_program_scene）。"""
        await self.set_current_program_scene(scene_name)

    # ---------- 录制 / 直播 ----------

    async def start_record(self) -> None:
        await self.request(models.OBSEventType.RecordEventType.START_RECORD)

    async def stop_record(self) -> None:
        await self.request(models.OBSEventType.RecordEventType.STOP_RECORD)

    async def toggle_record(self) -> dict:
        return await self.request(models.OBSEventType.RecordEventType.TOGGLE_RECORD)

    async def get_record_status(self) -> dict:
        return await self.request(models.OBSEventType.RecordEventType.GET_RECORD_STATUS)

    async def start_stream(self) -> None:
        await self.request(models.OBSEventType.StreamEventType.START_STREAM)

    async def stop_stream(self) -> None:
        await self.request(models.OBSEventType.StreamEventType.STOP_STREAM)

    async def get_stream_status(self) -> dict:
        return await self.request(models.OBSEventType.StreamEventType.GET_STREAM_STATUS)

    # ---------- 工具声明 ----------

    def get_tools(self) -> List[ToolFunction]:
        return [
            ToolFunction(
                name="switch_scene",
                description="切换 OBS 当前场景",
                parameters=ToolFunctionParameters(
                    type="object",
                    properties={
                        "scene_name": {"type": "string", "description": "目标场景名称"},
                    },
                    required=["scene_name"],
                ),
            ),
            ToolFunction(
                name="get_scene_list",
                description="获取 OBS 场景列表",
                parameters=ToolFunctionParameters(type="object", properties={}, required=[]),
            ),
            ToolFunction(
                name="start_record",
                description="开始录制",
                parameters=ToolFunctionParameters(type="object", properties={}, required=[]),
            ),
            ToolFunction(
                name="stop_record",
                description="停止录制",
                parameters=ToolFunctionParameters(type="object", properties={}, required=[]),
            ),
            ToolFunction(
                name="toggle_record",
                description="切换录制状态",
                parameters=ToolFunctionParameters(type="object", properties={}, required=[]),
            ),
            ToolFunction(
                name="get_record_status",
                description="查询当前录制状态",
                parameters=ToolFunctionParameters(type="object", properties={}, required=[]),
            ),
            ToolFunction(
                name="start_stream",
                description="开始推流",
                parameters=ToolFunctionParameters(type="object", properties={}, required=[]),
            ),
            ToolFunction(
                name="stop_stream",
                description="停止推流",
                parameters=ToolFunctionParameters(type="object", properties={}, required=[]),
            ),
            ToolFunction(
                name="get_stream_status",
                description="查询推流状态",
                parameters=ToolFunctionParameters(type="object", properties={}, required=[]),
            ),
            ToolFunction(
                name="set_record_directory",
                description="设置录制文件保存目录",
                parameters=ToolFunctionParameters(
                    type="object",
                    properties={
                        "record_directory": {"type": "string", "description": "保存目录绝对路径"},
                    },
                    required=["record_directory"],
                ),
            ),
        ]
