"""PyO3 绑定包装

把 Rust 侧的原始对象包成符合 `protocol.py` 契约的对象。
职责仅限：参数校验、类型转换、错误翻译。**不含业务逻辑**。

对应清单：R3（不长期持有 Py 对象）/ R4（释放 GIL）/ R6（错误不丢）。
"""

from __future__ import annotations

import pickle
from typing import Any, Callable, Dict, Literal, Optional

try:
    import core as _core
except Exception as _exc:  # noqa: BLE001
    _core = None
    _IMPORT_ERROR = str(_exc)
else:
    _IMPORT_ERROR = ""


def available() -> bool:
    return _core is not None

# ─────────────────────────────────────────────────────────────
# 流
# ─────────────────────────────────────────────────────────────

class PyStream:
    """Rust 流的 Python 包装。

    Rust 侧以字节承载（`Vec<u8>`），这里用 pickle 做编解码。
    传不可 pickle 的对象会明确报错，不会静默丢数据。
    """

    def __init__(self, capacity: int = 64) -> None:
        if _core is None:
            raise RuntimeError(f"Rust 内核不可用: {_IMPORT_ERROR}")
        self._raw = _core.PyStream(capacity)  # type: ignore
        self._error: Optional[str] = None

    def push(self, item: Any, timeout: Optional[float] = None) -> None:
        try:
            data = pickle.dumps(item, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception as exc:  # noqa: BLE001
            raise TypeError(f"流数据无法序列化: {exc}") from exc
        self._raw.push(data, timeout)

    def pop(self, timeout: Optional[float] = None) -> Optional[Any]:
        raw = self._raw.pop(timeout)
        if raw is None:
            return None
        return pickle.loads(bytes(raw))

    def try_pop(self) -> Optional[Any]:
        raw = self._raw.try_pop()
        return pickle.loads(bytes(raw)) if raw is not None else None

    def finish(self) -> None:
        self._raw.finish()

    def fail(self, msg: str) -> None:
        self._error = str(msg)
        self._raw.fail(str(msg))

    def cancel(self) -> None:
        self._error = "cancelled"
        self._raw.cancel()

    def pause(self) -> None:
        self._raw.pause()

    def resume(self) -> None:
        self._raw.resume()

    def is_done(self) -> bool:
        return bool(self._raw.is_done())
    
    def __aiter__(self):
        return self

    async def __anext__(self):
        from .common._await import stream_anext

        return await stream_anext(
            self.try_pop,
            lambda t: self.pop(t), # type: ignore
            self.is_done,
            timeout=None,
            error_fn=lambda: self._error,
        )

    def __len__(self) -> int:
        return int(self._raw.len())
    
    @property
    def error(self) -> Optional[str]:
        return self._error


# ─────────────────────────────────────────────────────────────
# 事件总线 / 定时器（直接转发）
# ─────────────────────────────────────────────────────────────

class PyEventBus:
    """emit 永不阻塞。"""

    def __init__(self) -> None:
        if _core is None:
            raise RuntimeError(f"Rust 内核不可用: {_IMPORT_ERROR}")
        self._raw = _core.PyEventBus()  # type: ignore

    def subscribe(self, event: str, callback: Callable) -> int:
        return int(self._raw.subscribe(event, callback))

    def unsubscribe(self, event: str, sub_id: int) -> bool:
        return bool(self._raw.unsubscribe(event, int(sub_id)))

    def emit(self, event: str, payload: Optional[Dict[str, Any]] = None) -> int:
        return int(self._raw.emit(event, payload or {}))

    def subscriber_count(self, event: str) -> int:
        return int(self._raw.subscriber_count(event))

    def close(self) -> None:
        self._raw.close()


class PyTimer:
    """防抖不占 Python 线程。"""

    def __init__(self) -> None:
        if _core is None:
            raise RuntimeError(f"Rust 内核不可用: {_IMPORT_ERROR}")
        self._raw = _core.PyTimer()  # type: ignore

    def debounce(
        self,
        window_ms: int,
        max_wait_ms: int,
        callback: Callable,
        payload: Any = None,
    ) -> int:
        return int(self._raw.debounce(
            int(window_ms), int(max_wait_ms), callback, payload))

    def touch(self, timer_id: int) -> bool:
        return bool(self._raw.touch(int(timer_id)))

    def flush(self, timer_id: int) -> None:
        self._raw.flush(int(timer_id))

    def cancel(self, timer_id: int) -> bool:
        return bool(self._raw.cancel(int(timer_id)))

    def pending(self) -> int:
        return int(self._raw.pending())
