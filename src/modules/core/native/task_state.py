"""统一任务状态机（B1-07）。

为什么需要
──────────
任务状态目前是**字符串 + 口头约定**：Rust 侧返回
`"pending" / "running" / ...`，Python 侧各处自行比较字面量。
这带来三类真实故障：

1. **终态被覆盖**。任务已 completed/cancelled，迟到的事件
   （慢 chunk、超时回调、重试）又把状态改回 running。
   表现：用户看到"已完成"，后台还在往里写；取消后又冒出一段回复。
2. **取消/超时不可解释**。只知道"不是 done"，说不清是
   被取消了、超时了、还是真的失败了。
3. **状态名漂移**。一处写 `"cancelled"`、另一处写 `"canceled"`，
   比较时静默不命中，逻辑分支走进默认路径。

本模块把状态与转移收敛成**纯函数**，调用方不再比较字符串。

设计取舍
────────
* **只做判定，不做执行**。不碰 Rust 调度器，不 await，
  不持有任务对象——判定逻辑要能脱离并发环境单测。
* **终态不可逆**。这是 B1-07 的核心验收项。
* **映射外部状态而非拒绝**。Rust 侧可能返回未知字符串，
  映射成 `UNKNOWN` 而不是抛异常——诊断时"看到状态异常"
  比"整个状态查询崩掉"有用。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Dict, FrozenSet, Mapping, Tuple

# ─────────────────────────────────────────────────────────────
# 状态
# ─────────────────────────────────────────────────────────────


class TaskState(str, Enum):
    """任务生命周期状态。"""

    #: 已创建，尚未开始
    PENDING = "pending"
    #: 执行中
    RUNNING = "running"
    #: 成功结束
    COMPLETED = "completed"
    #: 失败结束
    FAILED = "failed"
    #: 被主动取消
    CANCELLED = "cancelled"
    #: 超时结束
    TIMED_OUT = "timed_out"
    #: 外部状态无法识别
    UNKNOWN = "unknown"


#: 终态。**不可被后续事件覆盖**（B1-07 验收）。
TERMINAL_STATES: FrozenSet[TaskState] = frozenset({
    TaskState.COMPLETED,
    TaskState.FAILED,
    TaskState.CANCELLED,
    TaskState.TIMED_OUT,
})

#: 非正常结束
UNSUCCESSFUL_TERMINALS: FrozenSet[TaskState] = frozenset({
    TaskState.FAILED,
    TaskState.CANCELLED,
    TaskState.TIMED_OUT,
})

#: 外部状态字符串 → 内部状态。
#: 刻意同时收录 `cancelled` 与 `canceled`：两种拼写都会从
#: 不同来源出现，漏掉一种就会静默走进 UNKNOWN。
_EXTERNAL_ALIASES: Dict[str, TaskState] = {
    "pending": TaskState.PENDING,
    "queued": TaskState.PENDING,
    "created": TaskState.PENDING,
    "running": TaskState.RUNNING,
    "started": TaskState.RUNNING,
    "completed": TaskState.COMPLETED,
    "done": TaskState.COMPLETED,
    "success": TaskState.COMPLETED,
    "succeeded": TaskState.COMPLETED,
    "finished": TaskState.COMPLETED,
    "failed": TaskState.FAILED,
    "error": TaskState.FAILED,
    "errored": TaskState.FAILED,
    "cancelled": TaskState.CANCELLED,
    "canceled": TaskState.CANCELLED,
    "aborted": TaskState.CANCELLED,
    "timeout": TaskState.TIMED_OUT,
    "timed_out": TaskState.TIMED_OUT,
    "timedout": TaskState.TIMED_OUT,
    "unknown": TaskState.UNKNOWN,
}


def normalize_state(raw: Any) -> TaskState:
    """把任意来源的状态值映射为 `TaskState`。

    无法识别时返回 `UNKNOWN` 而不是抛异常——
    状态查询不该因为一个陌生字符串就整体失败。
    """
    if isinstance(raw, TaskState):
        return raw
    if raw is None:
        return TaskState.UNKNOWN
    key = str(raw).strip().lower()
    if not key:
        return TaskState.UNKNOWN
    return _EXTERNAL_ALIASES.get(key, TaskState.UNKNOWN)


def is_terminal(state: Any) -> bool:
    return normalize_state(state) in TERMINAL_STATES


def is_successful(state: Any) -> bool:
    return normalize_state(state) == TaskState.COMPLETED


# ─────────────────────────────────────────────────────────────
# 转移判定
# ─────────────────────────────────────────────────────────────


class TransitionVerdict(str, Enum):
    """转移判定结果。低基数稳定值，不拼自由文本。"""

    #: 允许
    ALLOWED = "allowed"
    #: 目标就是当前状态（幂等，视为允许）
    NOOP = "noop"
    #: 终态被后续事件覆盖 —— 被拒绝
    TERMINAL_LOCKED = "terminal_locked"
    #: 非法的转移（如 pending 直接 completed，中间没经过 running）
    INVALID = "invalid"


#: 合法转移表。未列出的组合一律 INVALID。
_ALLOWED_TRANSITIONS: FrozenSet[Tuple[TaskState, TaskState]] = frozenset({
    (TaskState.PENDING, TaskState.RUNNING),
    (TaskState.PENDING, TaskState.CANCELLED),      # 还没跑就被取消
    (TaskState.PENDING, TaskState.TIMED_OUT),      # 排队太久超时
    (TaskState.RUNNING, TaskState.COMPLETED),
    (TaskState.RUNNING, TaskState.FAILED),
    (TaskState.RUNNING, TaskState.CANCELLED),
    (TaskState.RUNNING, TaskState.TIMED_OUT),
    # UNKNOWN 是可恢复的：外部状态一时读不出来，
    # 之后读到真实状态应能继续推进，不应永久卡死
    (TaskState.UNKNOWN, TaskState.PENDING),
    (TaskState.UNKNOWN, TaskState.RUNNING),
    (TaskState.UNKNOWN, TaskState.COMPLETED),
    (TaskState.UNKNOWN, TaskState.FAILED),
    (TaskState.UNKNOWN, TaskState.CANCELLED),
    (TaskState.UNKNOWN, TaskState.TIMED_OUT),
})


def can_transit(current: Any, target: Any) -> TransitionVerdict:
    """判定一次状态转移是否允许。**纯函数**。"""
    cur = normalize_state(current)
    tgt = normalize_state(target)

    if cur == tgt:
        return TransitionVerdict.NOOP

    if cur in TERMINAL_STATES:
        # 终态不可逆。这是唯一需要**明确拒绝**并告警的情形：
        # 它意味着有迟到事件试图改写已结束的任务
        return TransitionVerdict.TERMINAL_LOCKED

    if (cur, tgt) in _ALLOWED_TRANSITIONS:
        return TransitionVerdict.ALLOWED

    return TransitionVerdict.INVALID


def transition_allowed(current: Any, target: Any) -> bool:
    """能否转移。`NOOP` 视为允许（幂等写入不该报错）。"""
    return can_transit(current, target) in (
        TransitionVerdict.ALLOWED,
        TransitionVerdict.NOOP,
    )


# ─────────────────────────────────────────────────────────────
# 状态记录
# ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TaskRecord:
    """一个任务的状态记录。frozen：只能经 `advance()` 派生新记录。"""

    task_id: str = ""
    state: TaskState = TaskState.PENDING
    #: 进入终态的原因（稳定枚举值，不是自由文本）
    reason: str = ""
    #: 状态变更次数，用于发现"一个任务被反复改写"
    revision: int = 0
    #: 最近一次被拒绝的转移（诊断用）
    last_rejected: str = ""
    #: 被拒绝的次数。持续增长说明有事件源在乱写
    rejected_count: int = 0
    #: 关联的请求，便于用 request_id 串日志（B1-08）
    request_id: str = ""
    session_id: str = ""

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def successful(self) -> bool:
        return self.state == TaskState.COMPLETED

    def as_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "state": self.state.value,
            "reason": self.reason,
            "revision": self.revision,
            "last_rejected": self.last_rejected,
            "rejected_count": self.rejected_count,
            "request_id": self.request_id,
            "session_id": self.session_id,
        }


class AdvanceResult(str, Enum):
    OK = "ok"
    NOOP = "noop"
    REJECTED_TERMINAL = "rejected_terminal"
    REJECTED_INVALID = "rejected_invalid"


def advance(
    record: TaskRecord,
    target: Any,
    *,
    reason: str = "",
) -> Tuple[TaskRecord, AdvanceResult, str]:
    """推进状态。返回 `(新记录, 结果, 说明)`。

    为什么返回新记录而不原地改：`frozen` 保证交给调用方的快照
    不会被别的协程悄悄改写——并发下"读到一半状态变了"是最难查的 bug 之一。

    终态被覆盖时**保留原状态**并返回 REJECTED_TERMINAL，
    调用方应记警告：这是迟到事件的明确信号。
    """
    verdict = can_transit(record.state, target)

    if verdict == TransitionVerdict.NOOP:
        return record, AdvanceResult.NOOP, "状态未变"

    if verdict == TransitionVerdict.TERMINAL_LOCKED:
        return (
            replace(
                record,
                last_rejected=f"{record.state.value}->{normalize_state(target).value}",
                rejected_count=record.rejected_count + 1,
            ),
            AdvanceResult.REJECTED_TERMINAL,
            f"任务已处于终态 {record.state.value}，拒绝改为 "
            f"{normalize_state(target).value}",
        )

    if verdict == TransitionVerdict.INVALID:
        return (
            replace(
                record,
                last_rejected=f"{record.state.value}->{normalize_state(target).value}",
                rejected_count=record.rejected_count + 1,
            ),
            AdvanceResult.REJECTED_INVALID,
            f"非法转移 {record.state.value} -> {normalize_state(target).value}",
        )

    return (
        replace(
            record,
            state=normalize_state(target),
            reason=str(reason or ""),
            revision=record.revision + 1,
            last_rejected="",
        ),
        AdvanceResult.OK,
        "",
    )


# ─────────────────────────────────────────────────────────────
# 结束原因（可解释性）
# ─────────────────────────────────────────────────────────────


class StopReason(str, Enum):
    """任务结束的原因。稳定低基数，进日志与审计（§5）。

    为什么不用自由文本：调用方需要按原因分流（重试？提示用户？），
    自由文本无法做稳定判断，也无法做计数告警。
    """

    #: 正常跑完
    COMPLETED = "completed"
    #: 用户/上游主动取消
    CANCELLED = "cancelled"
    #: 超时（整体 deadline，不是某个子步骤）
    TIMED_OUT = "timeout"
    #: 执行抛异常
    ERROR = "error"
    #: 工具额度用尽
    TOOL_BUDGET_EXHAUSTED = "tool_budget_exhausted"
    #: 队列已满被拒（§8：满载时必须给明确可重试错误）
    QUEUE_FULL = "queue_full"
    #: 未知
    UNKNOWN = "unknown"

    @property
    def retryable(self) -> bool:
        """是否值得重试。

        `CANCELLED` 不该重试——用户主动取消后再自动跑一遍，
        是他明确不想要的行为。`TIMED_OUT` 也不该盲重试：
        同样的输入很可能再次超时，重试只会放大拥塞。
        """
        return self in (StopReason.QUEUE_FULL, StopReason.ERROR)


#: 结束原因 → 对应状态
_STOP_TO_STATE: Dict[StopReason, TaskState] = {
    StopReason.COMPLETED: TaskState.COMPLETED,
    StopReason.CANCELLED: TaskState.CANCELLED,
    StopReason.TIMED_OUT: TaskState.TIMED_OUT,
    StopReason.ERROR: TaskState.FAILED,
    #: 跑完了，只是工具额度用尽 —— 不该被记成失败
    StopReason.TOOL_BUDGET_EXHAUSTED: TaskState.COMPLETED,
    StopReason.QUEUE_FULL: TaskState.FAILED,
    StopReason.UNKNOWN: TaskState.FAILED,
}


def state_for_reason(reason: StopReason) -> TaskState:
    return _STOP_TO_STATE.get(reason, TaskState.FAILED)


def finish(
    record: TaskRecord, reason: StopReason
) -> Tuple[TaskRecord, AdvanceResult, str]:
    """按原因结束任务。终止语义的唯一入口。"""
    return advance(record, state_for_reason(reason), reason=reason.value)


# ─────────────────────────────────────────────────────────────
# 可解释的终态摘要
# ─────────────────────────────────────────────────────────────


def explain(record: TaskRecord) -> str:
    """给日志/UI 用的一句话说明。**不含正文与堆栈**。"""
    if not record.terminal:
        return f"任务 {record.task_id} 进行中（{record.state.value}）"
    if record.successful:
        extra = f"，原因：{record.reason}" if record.reason else ""
        return f"任务 {record.task_id} 已完成{extra}"
    why = record.reason or "未提供原因"
    return f"任务 {record.task_id} 未成功结束（{record.state.value}，{why}）"


def summarize(records: Mapping[str, TaskRecord]) -> Dict[str, Any]:
    """批量统计。用于 health/诊断接口，不进 prompt。"""
    total = len(records)
    by_state: Dict[str, int] = {}
    rejected = 0
    for rec in records.values():
        by_state[rec.state.value] = by_state.get(rec.state.value, 0) + 1
        rejected += rec.rejected_count
    return {
        "total": total,
        "by_state": by_state,
        "rejected_transitions": rejected,
        "all_terminal": all(r.terminal for r in records.values()) if total else True,
    }
