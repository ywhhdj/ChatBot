import asyncio
import os

from .base import BaseRuntime


class PaddleOCRRuntime(BaseRuntime):
    def __init__(self, endpoint):
        super().__init__(endpoint)
        self.ocr = None
        self.lang = endpoint.get("lang", "ch")

    async def _load(self):
        from paddleocr import PaddleOCR # type:ignore
        model_dir:str = self.endpoint.get("model_dir", "")
        device = self.endpoint.get("device", "auto")
        kwargs = dict(
            use_angle_cls=True,
            lang=self.lang,
            device=device,
        )
        if model_dir:
            kwargs.update(
                det_model_dir=os.path.join(model_dir, "det"), # type:ignore
                rec_model_dir=os.path.join(model_dir, "rec"), # type:ignore
                cls_model_dir=os.path.join(model_dir, "cls"), # type:ignore
            )
        loop = asyncio.get_event_loop()
        self.ocr = await loop.run_in_executor(None, lambda: PaddleOCR(**kwargs))

    async def _infer(self, payload):
        return await self.recognize(payload)

    async def recognize(self, payload: dict) -> str:
        await self.ensure_loaded()
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self.ocr.predict, payload["image"]) # type:ignore
        if isinstance(result, dict):
            return result.get("text", "")
        return ""

    def close(self):
        if self.ocr is not None:
            try:
                if hasattr(self.ocr, "close"):
                    self.ocr.close()
            except Exception:
                pass
            self.ocr = None
            try:
                import torch
                torch.cuda.empty_cache()
            except Exception:
                pass
        super().close()