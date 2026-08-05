from typing import Dict, Optional, TypedDict

from pydantic import BaseModel


class OllamaParams(TypedDict):
    model: str

class _OpenAIBaseParams(OllamaParams, TypedDict):
    temperature: float
    max_tokens: int
    top_p: float
    presence_penalty: float
    frequency_penalty: float

class ChatGPTParams(_OpenAIBaseParams, TypedDict):
    pass


class DeepSeekParams(_OpenAIBaseParams, TypedDict):
    pass

class LLMResponse(BaseModel):
    content: str
    tool_call_id: Optional[str] = None
    tool_calls: Optional[Dict[str, str]] = None
