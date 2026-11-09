"""供应商能力门面：LLM / TTS / ASR / OCR 四个单例"""

from __future__ import annotations
import threading
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional

from .. import keys
from ..models import Message, Role
from . import factory
from .manager import Provider, provider_manager

_SINGLETON_LOCK = threading.Lock()


def _message_to_dict(message: Any) -> Dict[str, Any]:
    """兼容 dict / Message 对象，并把枚举 role 转成字符串。"""
    if isinstance(message, dict):
        data: Dict[str, Any] = {
            "role": message.get("role", Role.USER),
            "content": message.get("content", ""),
        }
        for key in ("tool_calls", "tool_call_id"):
            if message.get(key):
                data[key] = message[key]
    else:
        data = {
            "role": getattr(message, "role", Role.USER),
            "content": getattr(message, "content", ""),
        }
        for key in ("tool_calls", "tool_call_id"):
            value = getattr(message, key, None)
            if value:
                data[key] = value
    for key in ("role", "content"):
        value = data.get(key)
        if value is not None and not isinstance(value, (str, int, float, bool, list, dict)):
            data[key] = getattr(value, "value", str(value))
    return data


class _BaseManager(ABC):
    """单例基类。子类各自持有 ``_instance``，锁在模块级共享。"""

    _initialized = False
    _instance = None

    def __new__(cls, *args, **kwargs):
        if "_instance" not in cls.__dict__:
            with _SINGLETON_LOCK:
                if "_instance" not in cls.__dict__:
                    cls._instance = None
        if cls.__dict__.get("_instance") is None:
            with _SINGLETON_LOCK:
                if cls.__dict__.get("_instance") is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._provider: Any = None
        self._last_provider: str = ""
        self._last_model: Optional[str] = None
        self._usage_totals: Dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "calls": 0,
        }
        self._initialized = True

    # ---------- 通用适配器管理 ----------

    capability:str = ""

    def _close_instance(self, instance: Any) -> None:
        if instance is None:
            return
        close = getattr(instance, "close", None)
        try:
            if callable(close):
                close()
        except Exception:  # noqa: BLE001
            pass

    def _replace(self, provider: str, model_id: Optional[str], **kwargs: Any) -> Any:
        """先构建新适配器，成功后再释放旧的。任何构建异常都保留现状"""
        new = factory.create_adapter(
            self.capability, 
            provider, 
            model_id=model_id, 
            **kwargs
        )
        self._accumulate_usage()
        old = self._provider
        self._provider = new
        self._last_provider = str(provider)
        self._last_model = model_id or getattr(new, "model_id", None)
        self._close_instance(old)
        return new

    def _usage_delta(self) -> Dict[str, int]:
        provider = self._provider
        if provider is None or not hasattr(provider, "get_usage"):
            return {}
        return dict(provider.get_usage())

    def _accumulate_usage(self) -> None:
        current = self._usage_delta()
        if not current:
            return
        # shim 的用量是"本实例累计"，切换 provider 时把旧值折进总计
        for key in self._usage_totals:
            self._usage_totals[key] += int(current.get(key, 0))

    def get_usage_snapshot(self) -> Dict[str, int]:
        """当前 provider 用量 + 历史切换前的累计。"""
        out = dict(self._usage_totals)
        for key, value in self._usage_delta().items():
            out[key] = out.get(key, 0) + int(value)
        return out

    @property
    def is_initialized(self) -> bool:
        return self._provider is not None

    @property
    def current_provider(self) -> str:
        return self._last_provider

    @property
    def current_model(self) -> Optional[str]:
        return self._last_model

    def get_available_providers(self) -> List[str]:
        return provider_manager.get_valid_providers(self.capability)

    def get_params(self) -> Dict[str, Any]:
        if self._provider is None:
            return {}
        getter = getattr(self._provider, "get_params", None)
        return dict(getter()) if callable(getter) else {} # type: ignore

    def stop(self) -> None:
        if self._provider is None:
            return
        self._accumulate_usage()
        self._close_instance(self._provider)
        self._provider = None
        self._last_provider = ""
        self._last_model = None

    @abstractmethod
    def initialize_provider(self, provider: str = "", **kwargs: Any) -> None:
        raise NotImplementedError

    @abstractmethod
    def init_provider_client(self, **kwargs: Any) -> Any:
        raise NotImplementedError


@Provider(name=keys.ProviderType.TTS)
class TTS(_BaseManager):
    capability = keys.ProviderType.TTS

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        super().__init__()
        from ..core.context.audio import AudioContext
        self.audio_context = AudioContext()

    def initialize_provider(
        self, 
        provider: str = "gptsovits",
        model_id: Optional[str] = None, 
        **kwargs: Any
    ) -> None:
        self._replace(provider or "gptsovits", model_id, **kwargs)

    def init_provider_client(self, **kwargs: Any) -> "TTS":
        if self._provider is None:
            raise ValueError("No TTSAdapter is initialized")
        self._provider.initialize_client(**kwargs)
        return self

    async def process_text(self, text: str, **kwargs: Any) -> bytes:
        if self._provider is None:
            raise ValueError("No TTSAdapter is initialized")
        result = await self._provider.generate_voice(text, **kwargs)
        self.audio_context.add_audio_chunk(result)
        self.audio_context.reset_current_audio(category="tts")
        return result

    async def process_text_stream(
        self, text: str, **kwargs: Any
    ) -> AsyncGenerator[bytes, None]:
        if self._provider is None:
            raise ValueError("No TTSAdapter is initialized")
        async for chunk in self._provider.generate_voice_stream(text, **kwargs):
            self.audio_context.add_audio_chunk(chunk)
            yield chunk
        self.audio_context.reset_current_audio(category="tts")

    def close(self) -> None:
        self.stop()


@Provider(name=keys.ProviderType.LLM)
class LLM(_BaseManager):
    capability = keys.ProviderType.LLM

    def __init__(self, llm_provider_type: str = "deepseek") -> None:
        if getattr(self, "_initialized", False):
            return
        super().__init__()
        self.llm_provider_type = llm_provider_type
        self.text_threshold = 10
        self.max_turns = 5

    def initialize_provider(
        self, provider: str = "deepseek", model_id: Optional[str] = None, **kwargs: Any
    ) -> None:
        self._replace(provider or "deepseek", model_id, **kwargs)

    def init_provider_client(self, **kwargs: Any) -> "LLM":
        if self._provider is None:
            raise ValueError("No LLMAdapter is initialized")
        self._provider.initialize_client(**kwargs)
        return self

    async def prompt_message(self, user_input: str, prompt: str) -> str:
        if self._provider is None:
            raise ValueError("No LLM is initialized")
        return await self._provider.generate_text(
            messages=[
                _message_to_dict(Message(role=Role.SYSTEM, content=prompt.strip())),
                _message_to_dict(Message(role=Role.USER, content=user_input.strip())),
            ],
            temperature=0.0,
            max_tokens=256,
        )

    async def process_message(
        self,
        messages: List[Any],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> str:
        if self._provider is None:
            raise ValueError("No LLM is initialized")
        clean = [_message_to_dict(m) for m in messages]
        return await self._provider.generate_text(
            clean, temperature=temperature, max_tokens=max_tokens, **kwargs
        )

    async def process_message_stream(
        self,
        messages: List[Any],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        if self._provider is None:
            raise ValueError("No LLM is initialized")
        clean = [_message_to_dict(m) for m in messages]
        async for chunk in self._provider.generate_text_stream(
            clean, temperature=temperature, max_tokens=max_tokens, **kwargs
        ):
            if chunk:
                yield chunk

    async def compress(self, prompt: str, system_prompt: str) -> str:
        if self._provider is None:
            return ""
        messages = [
            _message_to_dict(Message(role=Role.SYSTEM, content=system_prompt)),
            _message_to_dict(Message(role=Role.USER, content=prompt)),
        ]
        return await self._provider.generate_text(messages)

    def get_usage(self) -> Dict[str, int]:
        return self.get_usage_snapshot()

    def close(self) -> None:
        self.stop()


@Provider(name=keys.ProviderType.ASR)
class ASR(_BaseManager):
    capability = keys.ProviderType.ASR

    def initialize_provider(
        self, provider: str = "whisper", model_id: Optional[str] = None, **kwargs: Any
    ) -> None:
        self._replace(provider or "whisper", model_id, **kwargs)

    @property
    def is_initialized(self) -> bool:
        if self._provider is None:
            return False
        return bool(getattr(self._provider, "initialized", True))

    async def init_provider_client(self, **kwargs: Any) -> "ASR":
        if self._provider is None:
            raise ValueError("No ASRAdapter is initialized")
        await self._provider.initialize(**kwargs)
        return self

    async def init_asr(self, **kwargs: Any) -> "ASR":
        return await self.init_provider_client(**kwargs)

    async def process_audio(self, audio_bytes: bytes) -> str:
        if self._provider is None:
            raise RuntimeError("ASR provider is not initialized")
        return await self._provider.transcribe(audio_bytes)

    async def process_audio_stream(
        self, audio_bytes: bytes, is_final: bool = False
    ) -> AsyncGenerator[str, None]:
        if self._provider is None:
            raise RuntimeError("ASR provider is not initialized")
        async for text in self._provider.transcribe_stream(audio_bytes, is_final=is_final):
            yield text

    async def close(self) -> None:
        self.stop()


@Provider(name=keys.ProviderType.OCR)
class OCR(_BaseManager):
    capability = keys.ProviderType.OCR

    def initialize_provider(
        self, provider: str = "paddle", model_id: Optional[str] = None, **kwargs: Any
    ) -> None:
        self._replace(provider or "paddle", model_id, **kwargs)

    @property
    def is_initialized(self) -> bool:
        if self._provider is None:
            return False
        return bool(getattr(self._provider, "initialized", True))

    async def init_provider_client(self, **kwargs: Any) -> "OCR":
        if self._provider is None:
            raise RuntimeError("OCR provider is not initialized")
        await self._provider.init_ocr(**kwargs)
        return self

    async def recognize(self, image_bytes: bytes) -> str:
        if self._provider is None:
            raise RuntimeError("OCR provider is not initialized")
        return await self._provider.recognize(image_bytes)


@Provider(name=keys.ProviderType.IMAGE)
class Image(_BaseManager):
    capability = keys.ProviderType.IMAGE

    def initialize_provider(
        self, provider: str = "openai-image", model_id: Optional[str] = None, **kwargs: Any
    ) -> None:
        self._replace(provider or "openai-image", model_id, **kwargs)

    def init_provider_client(self, **kwargs: Any) -> "Image":
        if self._provider is None:
            raise ValueError("No ImageAdapter is initialized")
        self._provider.initialize_client(**kwargs)
        return self

    async def generate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self._provider is None:
            raise ValueError("No ImageAdapter is initialized")
        return await self._provider.generate(payload)

    def close(self) -> None:
        self.stop()


__all__ = ["LLM", "TTS", "ASR", "OCR", "Image"]
