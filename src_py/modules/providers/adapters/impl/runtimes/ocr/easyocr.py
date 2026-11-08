import asyncio
from ..base import BaseRuntime


class EasyOCRRuntime(BaseRuntime):
    def __init__(self, endpoint):
        super().__init__(endpoint)
        self.reader = None
        self.languages = endpoint.get("languages") or ["ch_sim", "en"]

    async def _load(self):
        import easyocr  # 第三方库；旧代码 import 了自己这个模块，必然 AttributeError
        loop = asyncio.get_event_loop()
        self.reader = await loop.run_in_executor(
            None, lambda: easyocr.Reader(self.languages, gpu=True) # type:ignore
        )

    async def _infer(self, payload):
        return await self.recognize(payload)

    async def recognize(self, payload: dict) -> str:
        await self.ensure_loaded()
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self.reader.readtext, payload["image"]) # type:ignore
        return "".join(r[1] for r in result)

    def close(self):
        self.reader = None
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass
        super().close()