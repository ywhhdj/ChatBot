"""本地运行时基类：模型只加载一次、加载过程不阻塞事件循环。"""
from __future__ import annotations

import asyncio
import threading
from typing import Any, Dict, Optional


class BaseRuntime:
    def __init__(self, endpoint: dict):
        self.endpoint = dict(endpoint)
        self._loaded = False
        self._load_lock: Optional[asyncio.Lock] = None
        self._state_lock = threading.RLock()

    def _get_load_lock(self) -> asyncio.Lock:
        # asyncio.Lock 在 3.10+ 不绑定 loop，但仍需实例级唯一，不能在每次调用时创建
        if self._load_lock is None:
            self._load_lock = asyncio.Lock()
        return self._load_lock

    async def ensure_loaded(self) -> None:
        if self._loaded:
            return
        async with self._get_load_lock():
            if self._loaded:
                return
            await self._load()
            with self._state_lock:
                self._loaded = True

    async def _load(self) -> None:
        """子类实现：加载模型。重 CPU/IO 操作应走 run_in_executor。"""
        raise NotImplementedError

    async def infer(self, payload: Dict[str, Any]):
        await self.ensure_loaded()
        return await self._infer(payload)

    async def _infer(self, payload: Dict[str, Any]):
        raise NotImplementedError

    async def stream(self, payload: Dict[str, Any]):
        """可选：本地流式推理。默认把整体结果作为单个 chunk 产出。"""
        result = await self.infer(payload)
        if isinstance(result, str) and result:
            yield result

    def close(self) -> None:
        """子类实现：释放模型。必须幂等。"""
        with self._state_lock:
            self._loaded = False
