from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, TypedDict

class RouteType(Enum):
    PURE_CHAT = "pure_chat" #纯聊天
    TOOL_CALL = "tool_call" #纯工具调用
    MIXED = "mixed" #混合模式

@dataclass
class RouteDecision:
    route_type: RouteType
    confidence: float = 0.0 # 0-1
    detected_intents: List[str] = field(default_factory=list) #检测到的意图
    suggested_services: List[str] = field(default_factory=list) #建议的服务
    reason: str = "" #决策原因
    timestamp: datetime = datetime.min #缓存时间戳
    
    def to_dict(self):
        return {
            "route_type": self.route_type.value,
            "confidence": self.confidence,
            "detected_intents": self.detected_intents,
            "suggested_services": self.suggested_services,
            "reason": self.reason
        }

@dataclass
class RouteDecisionCache:
    timestamp: datetime
    decision: RouteDecision

class KeyWords(TypedDict):
    tools: dict[str, list[str]]
    emotional: list[str]
