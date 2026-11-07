#供应商创建工厂
from typing import Literal

def create_tts_adapter(provider_name: Literal["gptSoVITS", "vits"]|str, **kwargs):
    if provider_name == "gptSoVITS":
        from .tts.adapter import GPTSoVITSAdapter
        return GPTSoVITSAdapter(**kwargs)
    elif provider_name == "vits":
        from .tts.adapter import VitsAdapter
        return VitsAdapter(**kwargs)
    else:
        raise ValueError(f"Invalid TTSProviderType: {provider_name}")

def create_llm_adapter(provider_name: Literal["deepseek", "chatgpt", "ollama"]|str, **kwargs):
    if provider_name == "deepseek":
        from .llm.adapter import DeepseekLLMAdapter
        return DeepseekLLMAdapter(**kwargs)
    elif provider_name == "chatgpt":
        from .llm.adapter import ChatGPTLLMAdapter
        return ChatGPTLLMAdapter(**kwargs)
    elif provider_name == "ollama":
        from .llm.adapter import OllamaLLMAdapter
        return OllamaLLMAdapter(**kwargs)
    else:
        raise ValueError(f"Invalid LLMProviderType: {provider_name}")

def create_asr_adapter(provider_name: Literal["whisper"]|str, **kwargs):
    if provider_name == "whisper":
        from .asr.adapter import WhisperASRAdapter
        return WhisperASRAdapter(**kwargs)
    else:
        raise ValueError(f"Invalid ASRProviderType: {provider_name}")

def create_ocr_adapter(provider_name: Literal["paddle", "easyocr", "umi"]|str, **kwargs):
    if provider_name == "paddle":
        from .ocr.adapter import PaddleOCRAdapter
        return PaddleOCRAdapter(**kwargs)
    elif provider_name == "easyocr":
        from .ocr.adapter import EasyOCRAdapter
        return EasyOCRAdapter(**kwargs)
    elif provider_name == "umi":
        from .ocr.adapter import UmiOCRAdapter
        return UmiOCRAdapter(**kwargs)
    else:
        raise ValueError(f"OCR provider {provider_name} is not supported")
