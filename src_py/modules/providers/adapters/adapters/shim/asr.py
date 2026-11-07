from core.adapter.transports import RUNTIME_REGISTRY
from .base import _ShimBase


class ASRShim(_ShimBase):
    capability = "asr"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._runtime = None
        self.initialized = False

    async def initialize(self, model_path="", **kwargs):
        ep = dict(self._cfg["endpoint"])
        if model_path:
            ep["model_dir"] = model_path
        for k in ("device", "dtype", "language", "beam_size", "sample_rate"):
            if k in {**self.init_params, **kwargs}:
                v = {**self.init_params, **kwargs}[k]
                if v is not None:
                    ep[k] = v
        rt_cls = RUNTIME_REGISTRY[ep["runtime"]]
        self._runtime = rt_cls(ep)
        await self._runtime.ensure_loaded()
        self.initialized = True

    async def transcribe(self, audio_bytes):
        if not self.initialized:
            await self.initialize()
        payload = {"audio": audio_bytes, **self.init_params}
        return await self._runtime.transcribe(payload)

    async def transcribe_stream(self, audio_bytes, is_final=False):
        if not self.initialized:
            await self.initialize()
        payload = {"audio": audio_bytes, "is_final": is_final, **self.init_params}
        async for text in self._runtime.transcribe_stream(payload):
            yield text

    def close(self):
        if self._runtime is not None:
            try:
                self._runtime.close()
            except Exception:
                pass
            self._runtime = None
        self.initialized = False
        super().close()