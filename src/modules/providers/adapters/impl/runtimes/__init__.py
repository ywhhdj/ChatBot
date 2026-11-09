"""本地运行时注册表（懒加载）。"""
from __future__ import annotations

import importlib
from typing import Any, Dict, Type

_RUNTIME_SPECS: Dict[str, tuple] = {
    "faster-whisper": (".ocr.faster_whisper", "FasterWhisperRuntime"),
    "paddleocr": (".ocr.paddleocr", "PaddleOCRRuntime"),
    "tesseract": (".ocr.tesseract", "TesseractRuntime"),
    "easyocr": (".ocr.easyocr", "EasyOCRRuntime"),
    "umiocr": (".ocr.umiocr", "UmiOCRRuntime"),
}

_CLASS_CACHE: Dict[str, Type[Any]] = {}


def get_runtime_class(name: str) -> Type[Any]:
    key = str(name or "")
    if key in _CLASS_CACHE:
        return _CLASS_CACHE[key]
    spec = _RUNTIME_SPECS.get(key)
    if spec is None:
        raise KeyError(f"未注册的本地运行时: {key}")
    module = importlib.import_module(spec[0], __package__)
    cls = getattr(module, spec[1])
    _CLASS_CACHE[key] = cls
    return cls


class _LazyRuntimeRegistry(dict):
    """保持 ``RUNTIME_REGISTRY[name]`` 的老用法，但取值时才解析类。"""

    def __init__(self, specs: Dict[str, tuple]) -> None:
        super().__init__({k: v[1] for k, v in specs.items()})

    def __getitem__(self, key: str) -> Type[Any]:
        return get_runtime_class(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return get_runtime_class(key)
        except (KeyError, ImportError):
            return default


RUNTIME_REGISTRY: Dict[str, Any] = _LazyRuntimeRegistry(_RUNTIME_SPECS)

__all__ = ["RUNTIME_REGISTRY", "get_runtime_class"]
