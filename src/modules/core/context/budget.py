"""Prompt token 预算（C0-03 / B2-04）。

为什么单独一个文件
──────────────────
预算策略是**纯函数**：输入一批片段和预算，输出保留/丢弃/截断的判定与报告。
它不该知道角色是什么、记忆从哪来、LLM 用哪家。拆出来后可以脱离
PromptBuilder 单独测，也便于后续接上"自适应"策略
（OptimizationPlan B2-04：不超预算，且保留来源与置信度）。

三条硬约束（来自 BackendDesign §11）
────────────────────────────────────
1. **先过滤，再排序，最后按预算组装** —— 顺序不能反，
   否则会出现"先截断记忆、后发现角色设定就超预算"的错配。
2. **不可降级的东西永不裁剪**：角色身份、输出规则，属于安全与人格边界；
   降级顺序见 BackendDesign §10（记忆 → detailed → 工具文档可裁，
   权限检查/会话隔离/删除语义不可裁）。
3. **裁剪可解释**：返回报告，说明每段用了多少 token、被丢还是被截断，
   便于日志与后续评估，而不是静默丢内容。

优先级语义：数值越小越重要（与 PromptSegment.priority 一致，10 = 角色身份）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

#: CJK 大致 1 字 ≈ 1 token；拉丁约 4 字符 ≈ 1 token。
#: `context/prompt.py` 的 estimate_tokens 委托到这里，
#: 保证预算裁剪与结果统计是同一把尺子。
_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")


def estimate_tokens(text: str) -> int:
    """统一的 token 估算。空文本为 0（不是 1 —— 空段不该占预算）。"""
    if not text:
        return 0
    cjk = len(_CJK_RE.findall(text))
    return max(1, int(cjk + (len(text) - cjk) / 4))


#: 可被裁剪的段类型。其余类型视为"边界"，永不裁剪。
DROPPABLE_TYPES = frozenset({
    "memory",        # 检索到的记忆
    "detailed",      # 详细记忆层
    "recent_context",
    "randomness",    # 本轮表达变化
    "skill",         # 技能目录
    "history",       # 近期对话
})

#: 永不裁剪：缺了就不是这个角色，或会破坏安全约束。
PROTECTED_TYPES = frozenset({
    "character",
    "output_rules",
    "task_rules",
    "task",          # 当前任务本身
    "task_result",   # 刚执行完的结果，丢了会导致答非所问
    "directive",     # 阶段指令（额度耗尽/切换上下文），丢了会回到错误模式
})


@dataclass(frozen=True)
class BudgetPolicy:
    """预算策略。frozen：一次构建过程中不应被中途修改。"""

    #: system prompt 的总 token 上限
    total_tokens: int = 3000
    #: 为用户输入、历史消息和模型生成预留的 token（不计入 system 上限）
    reserve_for_input: int = 512
    #: 可裁剪类型（默认 DROPPABLE_TYPES）
    droppable: frozenset = DROPPABLE_TYPES
    #: 单段超过该值时优先截断而非整段丢弃
    truncate_over: int = 800
    #: 截断后保留的最大字符数
    truncate_to_chars: int = 1200

    def allowed_for_system(self) -> int:
        """实际可用于 system prompt 的预算。"""
        return max(1, int(self.total_tokens) - int(self.reserve_for_input))

    def with_total(self, total_tokens: int) -> "BudgetPolicy":
        return replace(self, total_tokens=max(1, int(total_tokens)))


@dataclass
class SegmentUsage:
    """单个片段的预算消耗记录（用于日志与评估）。"""

    type: str
    priority: int
    tokens: int
    kept: bool = True
    truncated: bool = False
    dropped: bool = False
    reason: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "priority": self.priority,
            "tokens": self.tokens,
            "kept": self.kept,
            "truncated": self.truncated,
            "dropped": self.dropped,
            "reason": self.reason,
        }


@dataclass
class BudgetReport:
    """裁剪报告。构建完成后可整体记入日志（不含正文，只含类型与用量）。"""

    budget: int = 0
    used: int = 0
    dropped: List[str] = field(default_factory=list)
    truncated: List[str] = field(default_factory=list)
    segments: List[SegmentUsage] = field(default_factory=list)

    @property
    def within_budget(self) -> bool:
        return self.used <= self.budget

    @property
    def overflow(self) -> int:
        return max(0, self.used - self.budget)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "budget": self.budget,
            "used": self.used,
            "within_budget": self.within_budget,
            "overflow": self.overflow,
            "dropped": list(self.dropped),
            "truncated": list(self.truncated),
            "segments": [s.as_dict() for s in self.segments],
        }


def _segment_text(item: Any) -> str:
    """兼容 dict / PromptSegment（TypedDict 或 pydantic）两种形态。"""
    if isinstance(item, dict):
        return str(item.get("content", "") or "")
    return str(getattr(item, "content", "") or "")


def _segment_type(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("type", "") or "")
    return str(getattr(item, "type", "") or "")


def _segment_priority(item: Any) -> int:
    raw = item.get("priority", 100) if isinstance(item, dict) else getattr(item, "priority", 100)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 100


def _with_text(item: Any, text: str) -> Any:
    """返回改过正文的同型片段（保持 dict 或原对象类型）。"""
    if isinstance(item, dict):
        cloned = dict(item)
        cloned["content"] = text
        return cloned
    try:
        return replace(item, content=text)  # type: ignore[call-arg]
    except Exception:
        # 不可变或不支持 replace 的对象：退化为 dict，保证流程不中断
        return {"type": _segment_type(item), "priority": _segment_priority(item), "content": text}


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rstrip()
    # 尽量断在换行处，避免半句话
    nl = cut.rfind("\n")
    if nl > max_chars // 2:
        cut = cut[:nl]
    return cut + "\n…（已按 token 预算截断）"


def apply_budget(
    segments: Sequence[Any],
    policy: Optional[BudgetPolicy] = None,
) -> Tuple[List[Any], BudgetReport]:
    """按预算裁剪片段。

    算法
    ────
    1. 逐段计 token，登记用量；
    2. 保护段（角色/输出规则/任务）**无条件保留**，先占预算；
    3. 若已超预算：可裁剪段按 priority 从大到小（最不重要先丢）整段丢弃；
    4. 若丢弃完仍超：对剩余可裁剪段做单段截断（超 `truncate_over` 的先截）；
    5. 返回保留列表（按 priority 升序）+ 报告。

    注意：本函数**不排序**输出，排序由调用方按 priority 决定 ——
    裁剪与排序是两件事，混在一起就没法单独测。
    """
    policy = policy or BudgetPolicy()
    budget = policy.allowed_for_system()

    report = BudgetReport(budget=budget)
    usages: Dict[int, SegmentUsage] = {}
    for index, item in enumerate(segments):
        text = _segment_text(item)
        usages[index] = SegmentUsage(
            type=_segment_type(item),
            priority=_segment_priority(item),
            tokens=estimate_tokens(text),
        )

    def used_tokens(kept: Iterable[int]) -> int:
        return sum(usages[i].tokens for i in kept)

    protected = [
        i for i in range(len(segments))
        if _segment_type(segments[i]) not in policy.droppable
    ]
    droppable = [
        i for i in range(len(segments))
        if _segment_type(segments[i]) in policy.droppable
    ]

    kept: List[int] = list(protected)

    # 3) 整段丢弃：最不重要（priority 最大）的先丢
    if used_tokens(kept) > budget:
        for i in sorted(droppable, key=lambda x: (-usages[x].priority, x)):
            if used_tokens(kept) <= budget:
                break
            usages[i].kept = False
            usages[i].dropped = True
            usages[i].reason = "超出 token 预算，按优先级丢弃"
            kept = [k for k in kept if k != i]

    # 4) 仍超预算 → 截断可裁剪的大段
    if used_tokens(kept) > budget:
        for i in sorted(
            [k for k in kept if _segment_type(segments[k]) in policy.droppable],
            key=lambda x: (-usages[x].tokens, x),
        ):
            if used_tokens(kept) <= budget:
                break
            if usages[i].tokens < policy.truncate_over:
                continue
            segments = list(segments)
            segments[i] = _with_text(
                segments[i], _truncate(_segment_text(segments[i]), policy.truncate_to_chars)
            )
            usages[i].tokens = estimate_tokens(_segment_text(segments[i]))
            usages[i].truncated = True
            usages[i].reason = "超出 token 预算，截断保留要点"

    kept.sort(key=lambda i: usages[i].priority)
    report.used = used_tokens(kept)
    report.segments = [usages[i] for i in range(len(segments))]
    report.dropped = [u.type for u in report.segments if u.dropped]
    report.truncated = [u.type for u in report.segments if u.truncated]
    return [segments[i] for i in kept], report


def fit_history(
    history: Sequence[Dict[str, Any]],
    max_tokens: int,
    *,
    keep_last: int = 2,
) -> List[Dict[str, Any]]:
    """按预算裁剪近期对话。

    对话历史是**时序**数据，不能按优先级挑：丢中间的会造成上下文断裂。
    这里从最旧的一端开始丢，但永远保留最近 `keep_last` 条（通常含当前轮）。
    """
    if max_tokens <= 0:
        return list(history[-keep_last:]) if keep_last > 0 else []

    items = list(history)
    total = sum(estimate_tokens(str(m.get("content", ""))) for m in items)
    if total <= max_tokens:
        return items

    dropped = 0
    limit = max(0, len(items) - keep_last)
    while dropped < limit:
        oldest = items[0]
        total -= estimate_tokens(str(oldest.get("content", "")))
        items.pop(0)
        dropped += 1
        if total <= max_tokens:
            break
    return items
