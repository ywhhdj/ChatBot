import asyncio
from ..base import BaseRuntime


class UmiOCRRuntime(BaseRuntime):
    def __init__(self, endpoint):
        super().__init__(endpoint)
        self.ocr = None

    async def _load(self):
        from umiocr import UmiOCR # type:ignore
        self.ocr = UmiOCR()

    async def _infer(self, payload):
        return await self.recognize(payload)

    async def recognize(self, payload: dict) -> str:
        await self.ensure_loaded()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.ocr, payload["image"]) # type:ignore

    def close(self):
        if self.ocr is not None and hasattr(self.ocr, "close"):
            try:
                self.ocr.close()
            except Exception:
                pass
        self.ocr = None
        super().close()