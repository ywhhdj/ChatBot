"""用户输入防抖（TD18–TD22）。

为什么需要
──────────
用户打字是分段的："帮我" → "打开" → "浏览器"。
三条分开发 = 三轮 LLM 调用，每轮上下文都不完整，
意图路由会分别判成"闲聊 / 闲聊 / 工具"，全错。

设计
────
* **窗口内合并**：最后一条输入后 `idle_window`（默认 1.5s，可配 1–3s）
  内不再有新输入，才提交。
* **上限保护**：从**第一次**输入起算 `max_wait`（默认 3s）强制提交。
  否则用户一直说，窗口被无限续期，永远等不到响应。
* **追加而非替换**：合并用换行连接，保留两句边界。
  拼成"帮我打开浏览器"这种粘连会改变语义。
* **提交后开新窗口**：已提交之后再来的输入是新的一轮。

线程安全：WebSocket handler 与调度器线程都可能调用，全程持锁。
"""

from __future__ import annotations

import threading
import time
from typing import Callable, List, Optional, Tuple

from ..logger import logger

DEFAULT_IDLE_WINDOW = 1.5
DEFAULT_MAX_WAIT = 3.0


class InputDebouncer:
    """把用户连续输入合并成一条。

    两种用法：

    1. 回调模式（推荐）—— 构造时传 `on_submit`，窗口到期自动调用：

        debouncer = InputDebouncer(on_submit=handle)
        debouncer.feed("帮我")        # 缓冲
        debouncer.feed("打开浏览器")  # 缓冲并重置计时
        # 1.5s 后自动 on_submit("帮我\\n打开浏览器")

    2. 拉取模式 —— 不传回调，自行 poll：

        merged, should_submit = debouncer.feed(text)
        if should_submit:
            handle(merged)
    """

    def __init__(
        self,
        on_submit: Optional[Callable[[str], None]] = None,
        idle_window: float = DEFAULT_IDLE_WINDOW,
        max_wait: float = DEFAULT_MAX_WAIT,
        joiner: str = "\n",
    ) -> None:
        # TD18：窗口可配 1–3 秒
        self.idle_window = _clamp(float(idle_window or DEFAULT_IDLE_WINDOW), 0.1, 10.0)
        self.max_wait = _clamp(float(max_wait or DEFAULT_MAX_WAIT), 0.1, 30.0)
        if self.max_wait < self.idle_window:
            # 上限比窗口还短的话，窗口永远等不到，直接按窗口走
            self.max_wait = self.idle_window
        self.joiner = joiner
        self._on_submit = on_submit

        self._lock = threading.RLock()
        self._buffer: List[str] = []
        self._first_at: float = 0.0
        self._last_at: float = 0.0
        self._timer: Optional[threading.Timer] = None
        self._deadline_timer: Optional[threading.Timer] = None

    # ---------- 主入口 ----------

    def feed(self, text: str) -> Tuple[str, bool]:
        """喂入一段输入。

        返回 `(merged, should_submit)`：
        * `should_submit=False` —— 还在窗口内，继续等
        * `should_submit=True`  —— 已超过 `max_wait`，**调用方应立即提交**
        """
        text = (text or "").strip()
        if not text:
            return "", False

        with self._lock:
            now = time.monotonic()
            if not self._buffer:
                self._first_at = now
                # TD21：从第一次输入起算的硬上限
                self._arm_deadline()
            self._buffer.append(text)
            self._last_at = now
            merged = self.joiner.join(self._buffer)

            elapsed_total = now - self._first_at
            if elapsed_total >= self.max_wait:
                # 超过硬上限，立即提交（拉取模式下由调用方提交）
                self._cancel_timers()
                self._buffer = []
                if self._on_submit is not None:
                    self._fire(merged)
                    return merged, False
                return merged, True

            # 回调模式：重置窗口计时
            if self._on_submit is not None:
                self._arm_idle()
            return merged, False

    def flush(self) -> str:
        """立即提交缓冲区（用户点了发送 / 连接断开 / 切换会话）。"""
        with self._lock:
            self._cancel_timers()
            if not self._buffer:
                return ""
            merged = self.joiner.join(self._buffer)
            self._buffer = []
            if self._on_submit is not None:
                self._fire(merged)
            return merged

    def pending(self) -> str:
        """当前缓冲内容（不提交）。"""
        with self._lock:
            return self.joiner.join(self._buffer)

    def clear(self) -> None:
        with self._lock:
            self._cancel_timers()
            self._buffer = []

    @property
    def is_pending(self) -> bool:
        with self._lock:
            return bool(self._buffer)

    # ---------- 内部 ----------

    def _arm_idle(self) -> None:
        """重置空闲窗口计时器。"""
        self._cancel_idle()
        t = threading.Timer(self.idle_window, self._on_idle)
        t.daemon = True
        self._timer = t
        t.start()

    def _arm_deadline(self) -> None:
        self._cancel_deadline()
        t = threading.Timer(self.max_wait, self._on_deadline)
        t.daemon = True
        self._deadline_timer = t
        t.start()

    def _on_idle(self) -> None:
        with self._lock:
            if not self._buffer:
                return
            merged = self.joiner.join(self._buffer)
            self._buffer = []
            self._cancel_timers()
        if self._on_submit is not None:
            self._fire(merged)

    def _on_deadline(self) -> None:
        self._on_idle()

    def _fire(self, text: str) -> None:
        try:
            self._on_submit(text)  # type: ignore[misc]
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[Debouncer] on_submit 失败: {exc}")

    def _cancel_idle(self) -> None:
        t = self._timer
        self._timer = None
        if t is not None:
            try:
                t.cancel()
            except Exception:  # noqa: BLE001
                pass

    def _cancel_deadline(self) -> None:
        t = self._deadline_timer
        self._deadline_timer = None
        if t is not None:
            try:
                t.cancel()
            except Exception:  # noqa: BLE001
                pass

    def _cancel_timers(self) -> None:
        self._cancel_idle()
        self._cancel_deadline()


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
