import asyncio
import threading


class BaseRuntime:
    def __init__(self, endpoint: dict):
        self.endpoint = dict(endpoint)
        self._loaded = False
        self._lock = threading.Lock()

    async def ensure_loaded(self):
        if self._loaded:
            return
        async with asyncio.Lock():  # 简化：单进程下够用
            if self._loaded:
                return
            await self._load()
            self._loaded = True

    async def _load(self):
        """子类实现：加载模型。"""
        raise NotImplementedError

    async def infer(self, payload: dict):
        await self.ensure_loaded()
        return await self._infer(payload)

    async def _infer(self, payload: dict):
        raise NotImplementedError

    def close(self):
        """子类实现：释放模型。必须幂等。"""
        self._loaded = False