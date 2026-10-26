from pydantic import ConfigDict, BaseModel


class SamplingParams(BaseModel):
    model_config = ConfigDict(extra="allow")   # 允许各家塞私有字段

    temperature: float = 0.7
    max_tokens: int = 1024
    top_p: float = 1.0
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    stop: str | list[str] | None = None
    seed: int | None = None
    stream: bool = False


class OllamaParams(SamplingParams):
    num_ctx: int | None = None
    num_predict: int | None = None
    keep_alive: str | int | None = None
    format: str | dict | None = None


class ChatGPTParams(SamplingParams):
    tool_choice: str | dict | None = None
    response_format: dict | None = None
    logit_bias: dict[str, int] | None = None
    user: str | None = None
    n: int = 1


class DeepSeekParams(SamplingParams):
    tool_choice: str | dict | None = None
    response_format: dict | None = None