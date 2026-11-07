from ..transports import RUNTIME_REGISTRY
from .base import _ShimBase


class OCRShim(_ShimBase):
    capability = "ocr"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._runtime = None
        self.initialized = False

    async def init_ocr(self, model_path="", **kwargs):
        ep = dict(self._cfg["endpoint"])
        if model_path:
            ep["model_dir"] = model_path
        for k in ("lang", "languages", "device"):
            if k in {**self.init_params, **kwargs}:
                v = {**self.init_params, **kwargs}[k]
                if v is not None:
                    ep[k] = v
        rt_cls = RUNTIME_REGISTRY[ep["runtime"]]
        self._runtime = rt_cls(ep)
        await self._runtime.ensure_loaded()
        self.initialized = True

    async def recognize(self, image_bytes):
        if self._runtime is None:
            await self.init_ocr()
        return await self._runtime.recognize({"image": image_bytes, **self.init_params}) # type:ignore

    def close(self):
        if self._runtime is not None:
            try:
                self._runtime.close()
            except Exception:
                pass
            self._runtime = None
        self.initialized = False
        super().close()