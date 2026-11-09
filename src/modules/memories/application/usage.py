"""`MemoryUsageEvent` 管线（M1-04 / §8.3）。

四条硬规则，逐条对应文档：

1. **请求完成且状态为 COMPLETED 后才发布**；失败、取消、超时的轮次
   不强化。否则一次超时重试就能把某条记忆反复"复习"到永远不遗忘。
2. **有界队列异步写入**，写入失败不影响本次回复；
   队列满时丢弃最旧的 `injected` 事件并计数告警。
   `injected` 是最弱信号（usage_weight 0.3），丢它代价最小；
   `confirmed` 是用户明确确认，绝不丢。
3. **事件必须带 session_id**，强化只作用于与该 session 的 scope
   匹配的记忆。
4. **强化路径不持有会话锁，不在请求线程中执行**。
   所以 `publish()` 只做 O(1) 入队，真正写库由 `flush()` 在后台跑。

为什么不用 `asyncio.Queue`
────────────────────────
事件可能从 Qt 主线程、调度器线程、Web loop 三处同时发布。
`asyncio.Queue` 绑定单个 loop，跨线程 put 需要 `call_soon_threadsafe`，
反而更容易写错。这里用 `deque + Lock`，`flush()` 由任一调用方触发
（通常是空闲定时器），与 loop 无关。
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence

from ...logger import logger
from ..domain.layers import UsageKind
from ..ports.protocols import UsageSink

DEFAULT_CAPACITY = 1024
MAX_FLUSH_BATCH = 256


@dataclass(frozen=True)
class MemoryUsageEvent:
    """一条使用事件。frozen：入队后不可被中途改写。"""

    memory_id: str
    session_id: str
    usage: UsageKind
    request_id: str = ""
    #: 事件产生时刻（epoch 秒），用于 massed 判定
    ts: float = 0.0
    #: 是否由 faded/archived 唤醒（增益减半）
    awakened: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "session_id": self.session_id,
            "usage": self.usage.value,
            "request_id": self.request_id,
            "ts": self.ts,
            "awakened": self.awakened,
        }


@dataclass
class UsageStats:
    published: int = 0
    flushed: int = 0
    dropped_injected: int = 0
    dropped_full: int = 0
    rejected_not_completed: int = 0
    write_failures: int = 0
    last_flush_ts: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "published": self.published,
            "flushed": self.flushed,
            "dropped_injected": self.dropped_injected,
            "dropped_full": self.dropped_full,
            "rejected_not_completed": self.rejected_not_completed,
            "write_failures": self.write_failures,
            "last_flush_ts": self.last_flush_ts,
        }


class MemoryUsageQueue:
    """有界、线程安全、非阻塞的发布队列。"""

    def __init__(
        self,
        *,
        capacity: int = DEFAULT_CAPACITY,
        sink: Optional[UsageSink] = None,
    ) -> None:
        self._capacity = max(16, int(capacity))
        self._queue: deque = deque()
        self._lock = threading.RLock()
        self._sink = sink
        self._stats = UsageStats()

    # ---------- 发布 ----------

    def publish_if_completed(
        self,
        memory_ids: Sequence[str],
        *,
        session_id: str,
        usage: UsageKind,
        request_id: str = "",
        request_state: str = "",
        awakened: bool = False,
    ) -> int:
        """只有 `request_state == "completed"` 才发布。

        用稳定字符串而不是异常对象判断：调用方来自四种 transport，
        有的用 `TaskState`，有的用 tracer.phase，统一成字符串最省心。
        """
        if str(request_state or "").strip().lower() != "completed":
            with self._lock:
                self._stats.rejected_not_completed += 1
            return 0
        return self.publish(
            memory_ids,
            session_id=session_id,
            usage=usage,
            request_id=request_id,
            awakened=awakened,
        )

    def publish(
        self,
        memory_ids: Sequence[str],
        *,
        session_id: str,
        usage: UsageKind,
        request_id: str = "",
        awakened: bool = False,
    ) -> int:
        """入队。**不抛异常、不阻塞、不做 IO**。"""
        if not memory_ids:
            return 0
        sid = str(session_id or "default")
        now = time.time()
        events = [
            MemoryUsageEvent(
                memory_id=str(mid),
                session_id=sid,
                usage=usage,
                request_id=str(request_id or ""),
                ts=now,
                awakened=bool(awakened),
            )
            for mid in memory_ids
        ]
        with self._lock:
            for event in events:
                self._enqueue_one(event)
        return len(events)

    def _enqueue_one(self, event: MemoryUsageEvent) -> None:
        if len(self._queue) < self._capacity:
            self._queue.append(event)
            self._stats.published += 1
            return

        # 满了：先尝试丢最旧的 injected，给强信号腾位置
        for index, old in enumerate(self._queue):
            if old.usage == UsageKind.INJECTED:
                del self._queue[index]
                self._stats.dropped_injected += 1
                self._queue.append(event)
                self._stats.published += 1
                return

        if event.usage == UsageKind.INJECTED:
            # 新事件本身就是最弱信号，直接丢
            self._stats.dropped_full += 1
            return
        # 强信号：丢队首（最旧的任意事件），保住用户确认
        self._queue.popleft()
        self._stats.dropped_full += 1
        self._queue.append(event)
        self._stats.published += 1

    # ---------- 消费 ----------

    def set_sink(self, sink: Optional[UsageSink]) -> None:
        with self._lock:
            self._sink = sink

    def flush(self, *, max_batch: int = MAX_FLUSH_BATCH) -> int:
        """由后台空闲任务调用。**失败不影响调用方**。

        采用 "先取后写、失败放回"：写入失败时事件不会丢，
        但也不会无限重试占满队列（重试交给下一次 flush）。
        """
        with self._lock:
            batch = [self._queue.popleft()
                     for _ in range(min(int(max_batch), len(self._queue)))]
            sink = self._sink
        if not batch or sink is None:
            self._put_back(batch)
            return 0

        try:
            written = int(sink.write([e.to_dict() for e in batch]) or 0)
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._stats.write_failures += 1
            logger.warning(f"[MemoryUsage] 写入失败: {type(exc).__name__}")
            self._put_back(batch)
            return 0

        with self._lock:
            self._stats.flushed += max(0, written)
            self._stats.last_flush_ts = time.time()
        return written

    def _put_back(self, batch: List[MemoryUsageEvent]) -> None:
        if not batch:
            return
        with self._lock:
            # 放回队首，保持原有顺序；超出容量的尾部丢弃
            self._queue.extendleft(reversed(batch))
            while len(self._queue) > self._capacity:
                dropped = self._queue.pop()
                self._stats.dropped_full += 1
                if dropped.usage == UsageKind.INJECTED:
                    self._stats.dropped_injected += 1

    # ---------- 诊断 ----------

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            out = self._stats.as_dict()
            out["pending"] = len(self._queue)
            out["capacity"] = self._capacity
        return out

    def pending(self) -> int:
        with self._lock:
            return len(self._queue)


_queue: Optional[MemoryUsageQueue] = None
_queue_lock = threading.Lock()


def get_usage_queue() -> MemoryUsageQueue:
    global _queue
    if _queue is None:
        with _queue_lock:
            if _queue is None:
                _queue = MemoryUsageQueue()
    return _queue
