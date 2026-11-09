from enum import Enum
class RouteType(Enum):
    PURE_CHAT = "pure_chat"  # 纯聊天
    TOOL_CALL = "tool_call"  # 纯工具调用
    MIXED = "mixed"          # 混合模式