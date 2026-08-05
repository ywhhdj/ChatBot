from __future__ import annotations
from abc import ABC, abstractmethod
import asyncio
import json
import threading
from typing import Any, AsyncGenerator, Optional
from inspect import iscoroutinefunction
from ..logger import logger
from ..manager.task import decorator
from ..manager.pipeline import Pipeline
from ..types import common
from ..tools.models import AITool
from . import enum

def _message_to_dict(message: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "role": getattr(message, "role", common.Role.USER),
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
    _lock = threading.Lock()
    _instance = None

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True

    def __new__(cls,*args,**kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    @property
    @abstractmethod
    def is_initialized(self) -> bool:
        raise NotImplementedError
    
    @abstractmethod
    def get_available_providers(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def intialize_provider(self, provider = None,**kwargs):
        raise NotImplementedError
    
    @abstractmethod
    def init_provider_client(self, **kwargs):
        raise NotImplementedError
    
    @abstractmethod
    def stop(self):
        raise NotImplementedError

@Pipeline(name=enum.AdapterType.TTS)
class TTS(_BaseManager):

    def __init__(self) -> None:
        super().__init__()
        self._provider = None
        from ..context.audio import AudioContext
        self.audio_context = AudioContext()

    def get_available_providers(self) -> list[str]:
        return list(enum.TTSProviderType.__members__.values())

    @property
    def is_initialized(self) -> bool:
        return self._provider is not None

    def get_params(self) -> dict[str, Any]:
        return self._provider.get_params() if self._provider else {}

    async def stop(self):
        if self._provider is None:
            return
        await self._provider.close()
        self._provider = None

    async def process_text(self, text: str) -> bytes:
        if self._provider is None:
            raise ValueError("No TTSAdapter is initialized")
        result = await self._provider.generate_voice(text)
        self.audio_context.add_audio_chunk(result)
        self.audio_context.reset_current_audio(category="tts")
        return result

    @decorator.stream_task_scheduler
    async def process_text_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        if self._provider is None:
            raise ValueError("No TTSAdapter is initialized")
        async for chunk in self._provider.generate_voice_stream(text):
            self.audio_context.add_audio_chunk(chunk)
            yield chunk
            await asyncio.sleep(0.05)
        self.audio_context.reset_current_audio(category="tts")

    from .adapters.tts.adapter import _TTSBaseAdapter
    def intialize_provider(
            self, 
            tts_provider: Optional[enum.TTSProviderType] = None,
            **kwargs
        ) -> None:
        if tts_provider == enum.TTSProviderType.GPTSoVITS:
            from .adapters.tts.adapter import GPTSoVITSAdapter
            self._provider = GPTSoVITSAdapter(**kwargs)
        elif tts_provider == enum.TTSProviderType.Vits:
            from .adapters.tts.adapter import VitsAdapter
            self._provider = VitsAdapter(**kwargs)
        else:
            raise ValueError(f"Invalid TTSProviderType: {tts_provider}")
    
    @decorator.sync_task_scheduler
    def init_provider_client(self, **kwargs: Any):
        if self._provider is None:
            raise ValueError("No TTSAdapter is initialized")
        self._provider.initialize_client(**kwargs)
    
    async def close(self):
        if self._provider is None:
            return
        await self._provider.close()
        self._provider = None

@Pipeline(name=enum.AdapterType.LLM)
class LLM(_BaseManager):


    def __init__(
        self,
        llm_provider_type: str = "deepseek"
    ):
        super().__init__()
        self.llm_provider_type: str = llm_provider_type
        self.text_threshold = 10
        self.max_turns=5
        self.service_orch=None

    
    def get_available_providers(self) -> list[str]:
        return list(enum.LLMProviderType.__members__.values())
    
    @decorator.sync_task_scheduler
    def init_provider_client(self, **kwargs: Any):
        if self._provider is None:
            raise ValueError("No LLMAdapter is initialized")
        self._provider.initialize_client(*kwargs)


    @property
    def is_initialized(self) -> bool:
        return self._provider is not None

    def get_params(self) -> Optional[dict[str, Any]]:
        if self._provider is None:
            return None
        return self._provider.get_params()

    def stop(self):
        if self._provider is None:
            return
        self._provider.close()
        self._provider = None

    from .adapters.llm.adapter import _LLMBaseAdapter
    def intialize_provider(
            self,
            llm_provider: Optional[enum.LLMProviderType] = enum.LLMProviderType.DeepSeek,
            **kwargs
        ):
        if llm_provider == enum.LLMProviderType.DeepSeek:
            from .adapters.llm.adapter import DeepseekLLMAdapter
            self._provider = DeepseekLLMAdapter(**kwargs)
        elif llm_provider == enum.LLMProviderType.ChatGPT:
            from .adapters.llm.adapter import ChatGPTLLMAdapter
            self._provider = ChatGPTLLMAdapter(**kwargs)
        elif llm_provider == enum.LLMProviderType.Ollama:
            from .adapters.llm.adapter import OllamaLLMAdapter
            self._provider = OllamaLLMAdapter(**kwargs)
        else:
            raise ValueError(f"Invalid LLMProviderType: {llm_provider}")
        if self.service_orch is None:
            from ..tools.ctl import ServiceOrchestrator
            self.service_orch=ServiceOrchestrator(
                config={
                    "max_rounds": 5,
                    "exec_mode": "sequential",
                    "stop_on_fatal": False,
                    "external_skill_dir": "skills",
                }
            )
    

    async def prompt_message(
        self,
        user_input: str,
        prompt: str,
    ) -> str:
        if self._provider is None:
            raise ValueError("No LLM is initialized")
        return await self._provider.generate_text(
            messages=[
                _message_to_dict(common.Message(
                    role=common.Role.SYSTEM,
                    content=prompt.strip()
                )),
                _message_to_dict(common.Message(
                    role=common.Role.USER,
                    content=user_input.strip()
                ))
            ],
            temperature=0.7,
            max_tokens=1024
        )

    async def process_message(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 1024
    ) -> str:
        if self._provider is None:
            raise ValueError("No LLM is initialized")
        if self._provider is None:
            return ""
        answer = await self._provider.generate_text(
            messages, 
            temperature=temperature, 
            max_tokens=max_tokens
        )
        return answer
    
    @decorator.stream_task_scheduler
    async def process_message_stream(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 1024
    ) -> AsyncGenerator[str, None]:
        if self._provider is None:
            raise ValueError("No LLM is initialized")
        answer=""
        async for chunk in self._provider.generate_text_stream(
            messages,
            temperature=temperature,
            max_tokens=max_tokens
        ):
            if chunk:
                answer += chunk
                yield chunk
                await asyncio.sleep(0.05)
    
    async def compress(self, prompt: str, system_prompt: str) -> str:
        if self._provider is None:
            return ""
        messages=[
            _message_to_dict(common.Message(role=common.Role.SYSTEM, content=system_prompt)),
            _message_to_dict(common.Message(role=common.Role.USER, content=prompt))
        ]
        return await self._provider.generate_text(messages)
    
    def close(self):
        if self._provider is None:
            return
        self._provider.close()
        self._provider = None

@Pipeline(name=enum.AdapterType.ASR)
class ASR(_BaseManager):
    def __init__(self) -> None:
        super().__init__()
        self._provider = None
    
    def stop(self):
        if self._provider is None:
            return
        self._provider.close()
        self.init=False
    
    @property
    def is_initialized(self) -> bool:
        return self._provider is not None and self._provider.initialized
    
    def get_available_providers(self) -> list[str]:
        return list(enum.ASRProviderType.__members__.values())
    
    from .adapters.asr.adapter import _ASRBaseAdapter
    def intialize_provider(
            self, 
            asr_provider: Optional[enum.ASRProviderType] = None,
            **kwargs
        ) -> None:
        if asr_provider == enum.ASRProviderType.OPENAI_WISPER:
            from .adapters.asr.adapter import WhisperASRAdapter
            self._provider = WhisperASRAdapter(**kwargs)
        # elif asr_provider == enum.ASRProviderType.BAIDU:
        #     from .adapters.asr.adapter import BaiduASRAdapter
        #     self._provider = BaiduASRAdapter(**kwargs)
        # elif asr_provider == enum.ASRProviderType.TENCENT_CLOUD:
        #     from .adapters.asr.adapter import TencentCloudASRAdapter
        #     self._provider = TencentCloudASRAdapter(**kwargs)
        else:
            raise ValueError(f"ASR provider {asr_provider} is not supported")
    
    @decorator.async_task_scheduler
    async def init_asr(self,*args,**kwargs):
        if self._provider is None:
            raise RuntimeError("ASR provider is not initialized")
        await self._provider.initialize(*args,**kwargs)

    
    async def process_audio(self, audio_bytes: bytes):
        if self._provider is None:
            raise RuntimeError("ASR provider is not initialized")
        return await self._provider.transcribe(audio_bytes)

    @decorator.stream_task_scheduler
    async def process_audio_stream(self, audio_bytes: bytes, is_final: bool=False) -> AsyncGenerator[str, None]:
        if self._provider is None:
            raise RuntimeError("ASR provider is not initialized")
        async for text in self._provider.transcribe_stream(audio_bytes, is_final=is_final):
            yield text

    async def close(self):
        if self._provider is None:
            return
        if iscoroutinefunction(self._provider.close):
            await self._provider.close()
        else:
            self._provider.close()
        self._provider = None
    
    @decorator.async_task_scheduler
    async def init_provider_client(self, **kwargs):
        if self._provider is None:
            raise ValueError("No ASRAdapter is initialized")
        await self._provider.initialize(**kwargs)

@Pipeline(name=enum.AdapterType.OCR)
class OCR(_BaseManager):


    def __init__(self) -> None:
        super().__init__()
        self._provider = None
        self.init = False
    
    def get_available_providers(self) -> list[str]:
        return list(enum.OCRProviderType.__members__.values())
    
    @property
    def is_initialized(self) -> bool:
        return self._provider is not None and self.init
    
    from .adapters.ocr.adapter import _OCRBaseAdapter
    def intialize_provider(
            self, 
            provider: Optional[enum.OCRProviderType] = None,
            **kwargs
        ) -> None:
        if provider == enum.OCRProviderType.Paddle:
            from .adapters.ocr.adapter import PaddleOCRAdapter
            self._provider = PaddleOCRAdapter(**kwargs)
        elif provider == enum.OCRProviderType.Easy:
            from .adapters.ocr.adapter import EasyOCRAdapter
            self._provider = EasyOCRAdapter(**kwargs)
        elif provider == enum.OCRProviderType.UMI:
            from .adapters.ocr.adapter import UmiOCRAdapter
            self._provider = UmiOCRAdapter(**kwargs)
        else:
            raise ValueError(f"OCR provider {provider} is not supported")
        
    @decorator.async_task_scheduler
    async def init_provider_client(self, **kwargs):
        if self._provider is None or self.init:
            raise RuntimeError("OCR provider is not initialized")
        await self._provider.init_ocr(**kwargs)
        self.init=True
    
    def stop(self):
        if self._provider is None:
            return
        self._provider.close()
        self._provider = None

    async def recognize(self, image_bytes: bytes) -> str:
        if self._provider is None:
            raise RuntimeError("OCR provider is not initialized")
        return await self._provider.recognize(image_bytes)
