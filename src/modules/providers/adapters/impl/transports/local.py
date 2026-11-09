"""本地运行时传输层：按 (runtime, model_dir, model) 复用已加载的模型。

修复：旧实现 ``self._closed`` 一旦为 True，``_get`` 又把它改回 False 后
继续往空字典里塞实例，逻辑自相矛盾；``RUNTIME_REGISTRY`` 还是**导入期**
就把 numpy / paddleocr / torch 全部拉起来，导致一个纯云端 LLM 请求也会
因为本机没装视觉依赖而启动失败。现在注册表是懒加载，且实例缓存加锁。
"""
from __future__ import annotations

import threading
from typing import Any, AsyncGenerator, Dict, Optional

from ..runtimes import RUNTIME_REGISTRY, get_runtime_class


class LocalTransport:
    def __init__(self) -> None:
        self._instances: Dict[Any, Any] = {}
        self._lock = threading.RLock()
        self._closed = False

    @staticmethod
    def _key(endpoint: Dict[str, Any]) -> Any:
        return (
            str(endpoint.get("runtime") or ""),
            str(endpoint.get("model_dir") or ""),
            str(endpoint.get("model_size") or ""),
            str(endpoint.get("device") or ""),
        )

    def _get(self, endpoint: Dict[str, Any]) -> Any:
        if self._closed:
            raise RuntimeError("LocalTransport 已关闭")
        runtime = str(endpoint.get("runtime") or "")
        if not runtime:
            raise RuntimeError("local endpoint 缺少 runtime")
        if runtime not in RUNTIME_REGISTRY:
            raise RuntimeError(
                f"未注册的本地运行时 {runtime!r}；可选: "
                + ", ".join(sorted(RUNTIME_REGISTRY.keys()))
            )
        key = self._key(endpoint)
        with self._lock:
            instance = self._instances.get(key)
            if instance is None:
                instance = get_runtime_class(runtime)(endpoint)
                self._instances[key] = instance
            return instance

    async def infer(self, endpoint: Dict[str, Any], payload: Dict[str, Any]) -> Any:
        """LLM 本地推理。runtime 需实现 ``infer(payload)``。"""
        return await self._get(endpoint).infer(payload)

    async def stream(
        self,
        endpoint: Dict[str, Any],
        payload: Dict[str, Any]
    ) -> AsyncGenerator[Any, None]:
        """本地流式推理。优先 ``runtime.stream``，否则退化成单块结果。
        """
        runtime = self._get(endpoint)
        stream = getattr(runtime, "stream", None)
        if callable(stream):
            async for chunk in stream(payload):
                yield chunk
            return
        result = await runtime.infer(payload)
        if result is not None:
            yield result

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            instances = list(self._instances.values())
            self._instances.clear()
        for rt in instances:
            try:
                rt.close()
            except Exception:  # noqa: BLE001
                pass
