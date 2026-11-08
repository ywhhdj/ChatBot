"""工具 / 函数声明模型（OpenAI 与 Anthropic 两种 schema）"""
from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

from ..routes.models import RouteType

PropertyType = Literal["string", "number", "boolean", "object", "array", "integer"]

AIPlatformType = Literal["openai", "anthropic"]


@dataclass
class ToolFunctionParameters:
    type: PropertyType = "object"
    properties: Dict[str, dict[str, Any]] = dc_field(default_factory=dict)
    required: list[str] = dc_field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "properties": self.properties,
            "required": self.required,
        }


@dataclass
class ToolFunction:
    name: str
    description: str
    parameters: ToolFunctionParameters = dc_field(default_factory=ToolFunctionParameters)
    required: Optional["list[str]"] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters.to_dict(),
        }

    def to_audit_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters.to_dict(),
            "required": list(self.required or []),
        }


ServiceTool = List[ToolFunction]


@dataclass
class OpenAITool:
    type: Literal["function"]
    function: ToolFunction

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "function": self.function.to_dict(),
        }


@dataclass
class AnthropicTool:
    name: str
    description: str
    input_schema: ToolFunctionParameters

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema.to_dict(),
        }


AITool = List[Union[OpenAITool, AnthropicTool, dict]]


class OrchestrationResult(BaseModel):
    route: RouteType = RouteType.PURE_CHAT
    chat_response: str = ""
    task_output: str = ""
    commands_executed: List[Dict[str, Any]] = Field(default_factory=list)
    task_summary: str = ""
    used_tokens_estimate: int = 0
    character_id: str = ""
    mood_after: int = 4
    affection_delta: int = 0
    #: 本轮消息 id（前端流式卡片按它聚合）
    message_id: str = ""
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    #: 跳过工具数量
    tools_skipped: int = 0
    #: 动态装配：本轮最终处于哪个阶段（tool_summary / forced_summary / service_work）
    stage: str = ""
    #: 可解释的结束原因（completed / cancelled / timeout / error ...）
    stop_reason: str = ""
    #: 本轮真实 token 用量（供应商返回 usage 时才有值，缺省全 0）
    usage: Dict[str, int] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "route": self.route.value if hasattr(self.route, "value") else str(self.route),
            **self.model_dump(),
        }
