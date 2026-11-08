"""ASR Shim：本地运行时 / HTTP 供应商的统一转写接口。"""
from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, Dict, Optional

from ..runtimes import get_runtime_class
from .base import ENDPOINT_KEYS, _ShimBase

_RUNTIME_KEYS = ("device", "dtype", "language", "beam_size", "sample_rate", "model_size")


class ASRShim(_ShimBase):
    capability = "asr"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._runtime = None
        self._init_lock: Optional[asyncio.Lock] = None
        self.initialized = False

    def _runtime_endpoint(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        ep = dict(self.endpoint)
        merged = {**self.init_params, **kwargs}
        for key in _RUNTIME_KEYS:
            value = merged.get(key)
            if value is not None:
                ep[key] = value
        if kwargs.get("model_path"):
            ep["model_dir"] = kwargs["model_path"]
        return ep

    async def initialize(self, model_path: str = "", **kwargs: Any) -> None:
        if self.initialized:
            return
        if self._init_lock is None:
            self._init_lock = asyncio.Lock()
        async with self._init_lock:
            if self.initialized:
                return
            ep = self._runtime_endpoint({"model_path": model_path, **kwargs})
            runtime_name = str(ep.get("runtime") or "")
            if not runtime_name:
                raise RuntimeError("ASR local endpoint 缺少 runtime")
            cls = get_runtime_class(runtime_name)
            runtime = cls(ep)
            await runtime.ensure_loaded()
            self._runtime = runtime
            self.initialized = True

    async def transcribe(self, audio_bytes: bytes) -> str:
        if not self.initialized:
            await self.initialize()
        payload = {"audio": audio_bytes, **self.request_params()}
        result = await self._runtime.transcribe(payload)  # type: ignore[union-attr]
        return str(result or "")

    async def transcribe_stream(
        self, audio_bytes: bytes, is_final: bool = False
    ) -> AsyncGenerator[str, None]:
        if not self.initialized:
            await self.initialize()
        payload = {
            "audio": audio_bytes,
            "is_final": is_final,
            **self.request_params(),
        }
        async for text in self._runtime.transcribe_stream(payload):  # type: ignore[union-attr]
            if text:
                yield text

    def close(self) -> None:
        if self._runtime is not None:
            try:
                self._runtime.close()
            except Exception:  # noqa: BLE001
                pass
            self._runtime = None
        self.initialized = False
        super().close()
