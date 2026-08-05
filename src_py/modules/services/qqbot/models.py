from dataclasses import dataclass, field
from typing import Dict, Optional, TypedDict

class QQBotEvent:
    class WebSocketEvent:
        HEARTBEAT = 10
        DISPATCH = 0
        RECONNECT = 7
        INVALID_SESSION = 9
    
    class MessageType:
        TEXT = 0
        MARKDOWN = 2
        ARK = 3
        EMBED = 4
        MEDIA = 7
    
    class LifecycleEvent:
        GUILD_CREATE = "GUILD_CREATE"
        GUILD_DELETE = "GUILD_DELETE"
        GUILD_UPDATE = "GUILD_UPDATE"
        CHANNEL_CREATE = "CHANNEL_CREATE"
        CHANNEL_DELETE = "CHANNEL_DELETE"
        CHANNEL_UPDATE = "CHANNEL_UPDATE"
        GROUP_ADD_ROBOT = "GROUP_ADD_ROBOT"
        GROUP_DEL_ROBOT = "GROUP_DEL_ROBOT"  # 机器人被踢出群
        GROUP_MSG_REJECT = "GROUP_MSG_REJECT"  # 机器人被禁言
        FRIEND_ADD = "FRIEND_ADD"  # 好友添加
        FRIEND_DEL = "FRIEND_DEL"  # 好友删除
        C2C_MSG_CREATE = "C2C_MSG_CREATE"  # 2C消息创建
        C2C_MSG_REJECT = "C2C_MSG_REJECT"  # 2C消息被禁言
        DIRECT_MESSAGE_CREATE = "DIRECT_MESSAGE_CREATE"  # 直接消息创建
        INTERACTION_CREATE = "INTERACTION_CREATE"

class QQBotData:
    @dataclass
    class QQBotResponse:
        opCode: int
        type: str
        seq: Optional[int] = None # 序列号，用于心跳确认
        data: Dict = field(default_factory=Dict)

    class QQBotInfo(TypedDict):
        id: str
        username: str
        avatar: str
        share_url: str
        welcome_msg: str
