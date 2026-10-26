from dataclasses import dataclass, field
from datetime import datetime
from typing import List, TypedDict
from ..types.router import RouteType

@dataclass
class RouteDecision:
    route_type: RouteType
    confidence: float = 0.0                                    # 0-1
    detected_intents: List[str] = field(default_factory=list)   # 检测到的意图
    suggested_services: List[str] = field(default_factory=list)  # 建议的服务
    reason: str = ""                                            # 决策原因
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self):
        return {
            "route_type": self.route_type.value,
            "confidence": self.confidence,
            "detected_intents": self.detected_intents,
            "suggested_services": self.suggested_services,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class RouteDecisionCache:
    timestamp: datetime
    decision: RouteDecision


class KeyWords(TypedDict):
    tools: "dict[str, list[str]]"
    emotional: "list[str]"
