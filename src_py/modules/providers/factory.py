# adapters/factory.py
import os
from .adapters.registry import Registry
from .adapters.adapters.shim import (
    LLMShim, ASRShim, OCRShim, TTSShim, SECRET_KEYS,
)

_registry = None

def get_registry():
    global _registry
    if _registry is None:
        _registry = Registry(os.getenv("PIPELINE_CONFIG_DIR", "config"))
    return _registry

def _split_kwargs(kwargs):
    secrets = {k: kwargs.pop(k) for k in list(kwargs) if k in SECRET_KEYS}
    return secrets, kwargs

def _make(shim_cls, capability:str, provider:str, kwargs):
    secrets, init_params = _split_kwargs(dict(kwargs))
    return shim_cls(get_registry(), provider, secrets, **init_params)

def create_adapter(capability:str, provider:str, **kwargs):
    table = {"llm": LLMShim, "asr": ASRShim, "ocr": OCRShim, "tts": TTSShim}
    if capability not in table:
        raise ValueError(f"Unknown capability: {capability}")
    return _make(table[capability], capability, provider, kwargs)