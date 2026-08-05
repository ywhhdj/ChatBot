from __future__ import annotations
from typing import Any, Dict, List
from pydantic import BaseModel, Field

from ..runtime import RuntimePath
from ..pipeline.enum import ASRProviderType, LLMProviderType, TTSProviderType


class _BaseConfig(BaseModel):
    enabled: bool = Field(default=True, description="是否启用")

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    def get_config_items(
        self,
        include_fields: List[str] | None = None,
        exclude_fields: List[str] | None = None,
    ) -> list[dict[str, Any]]:
        include_fields = include_fields or []
        exclude_fields = exclude_fields or []
        fields = include_fields or list(self.model_fields.keys())
        items: list[dict[str, Any]] = []
        for field_name in fields:
            if field_name in exclude_fields or field_name not in self.model_fields:
                continue
            field_info = self.model_fields[field_name]
            items.append({
                "name": field_name,
                "description": field_info.description,
                "value": getattr(self, field_name),
            })
        return items

    def update_from_dict(self, data: Dict[str, Any]) -> None:
        for key, value in data.items():
            if not hasattr(self, key):
                continue
            current = getattr(self, key)
            if isinstance(value, dict) and isinstance(current, _BaseConfig):
                current.update_from_dict(value)
            else:
                setattr(self, key, value)


class SkillsConfig(_BaseConfig):
    skill_dir: str = Field(default="skills", description="技能目录")


class SqliteConfig(_BaseConfig):
    enabled: bool = Field(default=False, description="是否启用 SQLite")
    db: str = Field(default="chatbot.db", description="数据库文件")


class LogConfig(_BaseConfig):
    level: str = Field(default="INFO", description="日志级别")
    format: str = Field(default="%(asctime)s - %(name)s - %(levelname)s - %(message)s", description="日志格式")
    datefmt: str = Field(default="%Y-%m-%d %H:%M:%S", description="日期格式")
    log_dir: str = Field(default=str(RuntimePath.get_log_dir()), description="日志目录")
    enable_log_file: bool = Field(default=False, description="是否写入日志文件")


class NetworkConfig(_BaseConfig):
    timeout: int = 10
    retry_count: int = 3
    delay: float = 1.0


class WebConfig(_BaseConfig):
    resources_path: str = "static"
    host: str = "127.0.0.1"
    port: int = 8080
    root_path: str = "/"
    allow_origins: List[str] = ["*"]
    allow_credentials: bool = True
    allow_methods: List[str] = ["*"]
    allow_headers: List[str] = ["*"]

    def update_web_config(self, config: Dict[str, Any]) -> None:
        self.update_from_dict(config)


class TTSConfig(_BaseConfig):
    provider: str = Field(default=TTSProviderType.GPTSoVITS.value, description="语音合成供应商")
    output_type: str = Field(default="mp3", description="输出文件类型")
    base_url: str = Field(default="http://127.0.0.1:9880", description="语音合成服务 URL")
    api_key: str = Field(default="", description="语音合成 API key")

    def update_tts_config(self, config: Dict[str, Any]) -> None:
        self.update_from_dict(config)


class LLMConfig(_BaseConfig):
    enabled: bool = Field(default=True, description="是否启用 LLM")
    provider: str = Field(default=LLMProviderType.DeepSeek.value, description="LLM 供应商")
    model: str = Field(default="deepseek-v4-flash", description="LLM 模型")
    api_key: str = Field(default="", description="LLM API key")
    base_url: str = Field(default="https://api.deepseek.com", description="LLM 服务 URL")
    active_perception: bool = Field(default=False, description="是否启用主动感知")
    wake_word: str = Field(default="ql", description="唤醒词")

    def update_llm_config(self, config: Dict[str, Any]) -> None:
        self.update_from_dict(config)


class ASRConfig(_BaseConfig):
    enabled: bool = Field(default=True, description="是否启用语音识别")
    provider: str = Field(default=ASRProviderType.OPENAI_WISPER.value, description="语音识别供应商")
    model: str = Field(default="base", description="语音识别模型")
    api_key: str = Field(default="", description="语音识别 API key")
    base_url: str = Field(default="", description="语音识别服务 URL")
    wake_word: str = Field(default="ql", description="唤醒词")

    def update_asr_config(self, config: Dict[str, Any]) -> None:
        self.update_from_dict(config)
