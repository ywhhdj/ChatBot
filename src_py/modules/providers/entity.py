from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional

from .. import keys
from ..logger import logger
from .manager import Provider, provider_manager
from ..core.native import decorator
from ..models import Message,Role
from . import factory


def _message_to_dict(message: Any) -> Dict[str, Any]:
    if isinstance(message, dict):
        data: Dict[str, Any] = {
            "role": message.get("role", Role.USER),
            "content": message.get("content", ""),
        }
        if message.get("tool_calls"):
            data["tool_calls"] = message["tool_calls"]
        if message.get("tool_call_id"):
            data["tool_call_id"] = message["tool_call_id"]
        return data

    data = {
        "role": getattr(message, "role", Role.USER),
        "content": getattr(message, "content", ""),
    }
    tool_calls = getattr(message, "tool_calls", None)
    tool_call_id = getattr(message, "tool_call_id", None)
    if tool_calls:
        data["tool_calls"] = tool_calls
    if tool_call_id:
        data["tool_call_id"] = tool_call_id
    return data


class _BaseManager(ABC):
    _initialized = False
    _lock = None  # 延迟创建，避免导入期依赖
    _instance = None

    def __new__(cls, *args, **kwargs):
        import threading

        if cls._lock is None:
            cls._lock = threading.Lock()
        # 关键：用 cls.__dict__ 判断，确保每个子类有自己的 _instance
        if "_instance" not in cls.__dict__:
            with cls._lock:
                if "_instance" not in cls.__dict__:
                    cls._instance = None
        if cls.__dict__.get("_instance") is None:
            with cls._lock:
                if cls.__dict__.get("_instance") is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True

    @property
    @abstractmethod
    def is_initialized(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_available_providers(self) -> List[str]:
        raise NotImplementedError

    @abstractmethod
    def initialize_provider(self, provider=None, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def init_provider_client(self, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def stop(self):
        raise NotImplementedError


@Provider(name=keys.ProviderType.TTS)
class TTS(_BaseManager):

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        super().__init__()
        self._provider = None
        from ..core.context.audio import AudioContext

        self.audio_context = AudioContext()
        self._last_provider = ""

    def get_available_providers(self) -> List[str]:
        return provider_manager.get_valid_providers(keys.ProviderType.TTS)

    @property
    def is_initialized(self) -> bool:
        return self._provider is not None

    def get_params(self) -> Dict[str, Any]:
        return self._provider.get_params() if self._provider else {}

    def stop(self) -> None:
        self.close()

    async def process_text(self, text: str,**kwargs) -> bytes:
        if self._provider is None:
            raise ValueError("No TTSAdapter is initialized")
        result = await self._provider.generate_voice(text,**kwargs)
        self.audio_context.add_audio_chunk(result)
        self.audio_context.reset_current_audio(category="tts")
        return result

    async def process_text_stream(self, text: str,**kwargs) -> AsyncGenerator[bytes, None]:
        if self._provider is None:
            raise ValueError("No TTSAdapter is initialized")
        async for chunk in self._provider.generate_voice_stream(text,**kwargs):
            self.audio_context.add_audio_chunk(chunk)
            yield chunk
        self.audio_context.reset_current_audio(category="tts")

    def initialize_provider(
        self,
        tts_provider: str = "gptSoVITS",
        **kwargs,
    ) -> None:
        if self._provider is not None:
            self.stop()
        self._provider = factory.create_adapter("tts", tts_provider, **kwargs)
        self._last_provider = tts_provider

    @decorator.sync_task_scheduler
    def init_provider_client(self, **kwargs: Any) -> None:
        if self._provider is None:
            raise ValueError("No TTSAdapter is initialized")
        self._provider.initialize_client(**kwargs)

    def close(self) -> None:
        if self._provider is None:
            return
        close_fn = getattr(self._provider, "close", None)
        if close_fn is None:
            self._provider = None
            return
        close_fn()
        self._provider = None


@Provider(name=keys.ProviderType.LLM)
class LLM(_BaseManager):

    def __init__(self, llm_provider_type: str = "deepseek") -> None:
        if getattr(self, "_initialized", False):
            return
        super().__init__()
        self.llm_provider_type: str = llm_provider_type
        self.text_threshold = 10
        self.max_turns = 5
        self._provider = None

    def get_available_providers(self) -> List[str]:
        return provider_manager.get_valid_providers(keys.ProviderType.LLM)

    @decorator.sync_task_scheduler
    def init_provider_client(self, **kwargs: Any) -> None:
        if self._provider is None:
            raise ValueError("No LLMAdapter is initialized")
        self._provider.initialize_client(**kwargs)

    @property
    def is_initialized(self) -> bool:
        return self._provider is not None

    def get_params(self) -> Optional[Dict[str, Any]]:
        if self._provider is None:
            return None
        return self._provider.get_params()

    def stop(self) -> None:
        if self._provider is None:
            return
        close_fn = getattr(self._provider, "close", None)
        if callable(close_fn):
            close_fn()
        self._provider = None

    def initialize_provider(
        self,
        llm_provider: str = "deepseek",
        **kwargs,
    ) -> None:
        if self._provider is not None:
            self.stop()
        self._provider = factory.create_adapter("llm",llm_provider, **kwargs)

    async def prompt_message(self, user_input: str, prompt: str) -> str:
        if self._provider is None:
            raise ValueError("No LLM is initialized")
        return await self._provider.generate_text(
            messages=[
                _message_to_dict(
                    Message(role=Role.SYSTEM, content=prompt.strip())
                ),
                _message_to_dict(
                    Message(role=Role.USER, content=user_input.strip())
                ),
            ],
            temperature=0.7,
            max_tokens=1024,
        )

    async def process_message(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ):
        if self._provider is None:
            raise ValueError("No LLM is initialized")
        return await self._provider.generate_text(
            messages, temperature=temperature, max_tokens=max_tokens
        )

    async def process_message_stream(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> AsyncGenerator[str, None]:
        if self._provider is None:
            raise ValueError("No LLM is initialized")
        async for chunk in self._provider.generate_text_stream(
            messages, temperature=temperature, max_tokens=max_tokens
        ):
            if chunk:
                yield chunk

    async def compress(self, prompt: str, system_prompt: str) -> str:
        if self._provider is None:
            return ""
        messages = [
            _message_to_dict(
                Message(role=Role.SYSTEM, content=system_prompt)
            ),
            _message_to_dict(Message(role=Role.USER, content=prompt)),
        ]
        return await self._provider.generate_text(messages)

    def close(self) -> None:
        self.stop()


@Provider(name=keys.ProviderType.ASR)
class ASR(_BaseManager):
    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        super().__init__()
        self._provider = None
        self.init = False
        self._last_provider=""

    def stop(self) -> None:
        if self._provider is None:
            return
        close_fn = getattr(self._provider, "close", None)
        if callable(close_fn):
            close_fn()
        self._provider = None
        self.init = False

    @property
    def is_initialized(self) -> bool:
        try:
            return self._provider is not None and bool(self._provider.initialized)
        except Exception:
            return self._provider is not None

    def get_available_providers(self) -> List[str]:
        return provider_manager.get_valid_providers(keys.ProviderType.ASR)

    def initialize_provider(self, asr_provider: str = "whisper", **kwargs) -> None:
        if self._provider is not None:
            self.stop()
        self._provider = factory.create_adapter("asr", asr_provider, **kwargs)
        self._last_provider = asr_provider

    @decorator.async_task_scheduler
    async def init_asr(self, *args, **kwargs) -> None:
        if self._provider is None:
            raise RuntimeError("ASR provider is not initialized")
        await self._provider.initialize(*args, **kwargs)
        self.init = True

    async def process_audio(self, audio_bytes: bytes):
        if self._provider is None:
            raise RuntimeError("ASR provider is not initialized")
        return await self._provider.transcribe(audio_bytes)

    async def process_audio_stream(
        self,
        audio_bytes: bytes,
        is_final: bool = False
    ) -> AsyncGenerator[str, None]:
        if self._provider is None:
            raise RuntimeError("ASR provider is not initialized")
        async for text in self._provider.transcribe_stream(audio_bytes, is_final=is_final):
            yield text

    async def close(self) -> None:
        self.stop()

    @decorator.async_task_scheduler
    async def init_provider_client(self, **kwargs) -> None:
        if self._provider is None:
            raise ValueError("No ASRAdapter is initialized")
        await self._provider.initialize(**kwargs)
        self.init = True


@Provider(name=keys.ProviderType.OCR)
class OCR(_BaseManager):

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        super().__init__()
        self._provider = None
        self.init = False
        self._last_provider = ""

    def get_available_providers(self) -> List[str]:
        return provider_manager.get_valid_providers(keys.ProviderType.OCR)

    @property
    def is_initialized(self) -> bool:
        return self._provider is not None and self.init

    def initialize_provider(self, provider: str = "paddle", **kwargs) -> None:
        if self._provider is not None:
            self.stop()
        self._provider = factory.create_adapter("ocr", provider, **kwargs)
        self._last_provider = provider

    @decorator.async_task_scheduler
    async def init_provider_client(self, **kwargs) -> None:
        if self._provider is None:
            raise RuntimeError("OCR provider is not initialized")
        if self.init:
            logger.debug("[OCR] 已初始化，跳过重复加载")
            return
        await self._provider.init_ocr(**kwargs)
        self.init = True

    def stop(self) -> None:
        if self._provider is None:
            return
        close_fn = getattr(self._provider, "close", None)
        if callable(close_fn):
            close_fn()
        self._provider = None
        self.init = False

    async def recognize(self, image_bytes: bytes) -> str:
        if self._provider is None:
            raise RuntimeError("OCR provider is not initialized")
        return await self._provider.recognize(image_bytes)
