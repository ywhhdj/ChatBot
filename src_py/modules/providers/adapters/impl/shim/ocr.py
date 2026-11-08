"""OCR Shim：本地运行时 / HTTP 供应商的统一识别接口。"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from ..runtimes import get_runtime_class
from .base import _ShimBase

_RUNTIME_KEYS = ("lang", "languages", "device", "dtype")


class OCRShim(_ShimBase):
    capability = "ocr"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._runtime = None
        self._init_lock: Optional[asyncio.Lock] = None
        self.initialized = False

    async def init_ocr(self, model_path: str = "", **kwargs: Any) -> None:
        if self.initialized:
            return
        if self._init_lock is None:
            self._init_lock = asyncio.Lock()
        async with self._init_lock:
            if self.initialized:
                return
            ep = dict(self.endpoint)
            merged = {**self.init_params, **kwargs}
            for key in _RUNTIME_KEYS:
                value = merged.get(key)
                if value is not None:
                    ep[key] = value
            if model_path:
                ep["model_dir"] = model_path
            runtime_name = str(ep.get("runtime") or "")
            if not runtime_name:
                raise RuntimeError("OCR local endpoint 缺少 runtime")
            runtime = get_runtime_class(runtime_name)(ep)
            await runtime.ensure_loaded()
            self._runtime = runtime
            self.initialized = True

    async def recognize(self, image_bytes: bytes) -> str:
        if not self.initialized:
            await self.init_ocr()
        payload = {"image": image_bytes, **self.request_params()}
        result = await self._runtime.recognize(payload)  # type: ignore[union-attr]
        return str(result or "")

    def close(self) -> None:
        if self._runtime is not None:
            try:
                self._runtime.close()
            except Exception:  # noqa: BLE001
                pass
            self._runtime = None
        self.initialized = False
        super().close()
