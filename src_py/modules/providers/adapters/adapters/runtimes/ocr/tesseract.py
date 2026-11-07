import asyncio
from .base import BaseRuntime


class TesseractRuntime(BaseRuntime):
    def __init__(self, endpoint):
        super().__init__(endpoint)
        self._fn = None
        self.lang = endpoint.get("lang", "chi_sim+eng")

    async def _load(self):
        from pytesseract import image_to_string # type:ignore
        self._fn = image_to_string

    async def _infer(self, payload):
        return await self.recognize(payload)

    async def recognize(self, payload: dict) -> str:
        await self.ensure_loaded()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self._fn(payload["image"], lang=payload.get("lang", self.lang)) # type:ignore
        )

    def close(self):
        self._fn = None
        super().close()