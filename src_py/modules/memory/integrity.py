"""记忆索引完整性：删除墓碑、索引对齐诊断、embedding 版本化。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple

# ─────────────────────────────────────────────────────────────
# 内容摘要（不存正文）
# ─────────────────────────────────────────────────────────────


def content_digest(text: str) -> str:
    """记忆正文的 sha256"""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


#: 空内容的摘要。用于"记不清原文"的场景——此时墓碑只能按 id 匹配，
#: 且必须标记为弱匹配（见 `Tombstone.match`）。
UNKNOWN_DIGEST = ""


# ─────────────────────────────────────────────────────────────
# 墓碑（B1-05）
# ─────────────────────────────────────────────────────────────


class DeleteReason(str, Enum):
    """删除原因。低基数稳定值，进审计不进 prompt（§5）。"""

    USER = "user"
    POLICY = "policy"
    RETENTION = "retention"
    COMPACTION = "compaction"
    RESTORE_CONFLICT = "restore_conflict"


@dataclass(frozen=True)
class Tombstone:
    """一条删除记录。**不含正文**。"""

    memory_id: int
    session_id: str = "default"
    digest: str = UNKNOWN_DIGEST
    deleted_at: float = 0.0
    reason: str = DeleteReason.USER.value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_id": int(self.memory_id),
            "session_id": str(self.session_id),
            "digest": str(self.digest),
            "deleted_at": float(self.deleted_at),
            "reason": str(self.reason),
        }

    @staticmethod
    def from_dict(raw: Any) -> Optional["Tombstone"]:
        if not isinstance(raw, dict):
            return None
        try:
            mid = int(raw.get("memory_id", -1))
        except (TypeError, ValueError):
            return None
        if mid < 0:
            return None
        return Tombstone(
            memory_id=mid,
            session_id=str(raw.get("session_id", "default") or "default"),
            digest=str(raw.get("digest", "") or ""),
            deleted_at=float(raw.get("deleted_at", 0.0) or 0.0),
            reason=str(raw.get("reason", DeleteReason.USER.value)),
        )

    def matches(self, memory_id: int, digest: str) -> bool:
        """这条记忆是否就是当年被删的那条。

        **同时比对 id 与内容摘要**。理由见模块注释的"id 复用"陷阱：
        只比 id 会误杀快照恢复后重用了同一 id 的新记忆。

        `digest` 为空（墓碑没记下原文）时退化为仅 id 匹配，
        这是弱匹配——宁可多挡一条，也不能让被删内容复活。
        """
        if int(memory_id) != self.memory_id:
            return False
        if not self.digest:
            return True
        return str(digest) == self.digest


def tombstone_for(
    memory_id: int,
    content: str = "",
    session_id: str = "default",
    reason: DeleteReason = DeleteReason.USER,
    deleted_at: float = 0.0,
) -> Tombstone:
    return Tombstone(
        memory_id=int(memory_id),
        session_id=str(session_id or "default"),
        digest=content_digest(content) if content else UNKNOWN_DIGEST,
        deleted_at=float(deleted_at),
        reason=reason.value if isinstance(reason, DeleteReason) else str(reason),
    )


def filter_resurrected(
    rows: Iterable[Mapping[str, Any]],
    tombstones: Iterable[Tombstone],
    *,
    id_key: str = "id",
    content_key: str = "content",
) -> List[Dict[str, Any]]:
    """剔除命中墓碑的记忆行。**纯函数**，不改输入。

    这是"删除后不能复活"的最后一道闸：
    无论数据来自实时查询、快照恢复还是缓存，
    注入 prompt 之前都要过一遍。
    """
    marks = list(tombstones)
    if not marks:
        return [dict(r) for r in rows]
    out: List[Dict[str, Any]] = []
    for row in rows:
        try:
            mid = int(row.get(id_key, -1))
        except (TypeError, ValueError):
            mid = -1
        digest = content_digest(str(row.get(content_key, "") or ""))
        if any(t.matches(mid, digest) for t in marks):
            continue
        out.append(dict(row))
    return out


def purge_before(tombstones: Iterable[Tombstone], cutoff_ts: float) -> List[Tombstone]:
    """清理早于 cutoff 的墓碑。

    墓碑不能无限增长（§6 日志/磁盘增长有上限），
    但也不能随便丢：丢掉的墓碑意味着对应记忆"可以复活"。
    所以清理只针对**足够老**的墓碑，且调用方需自行决定保留期。
    """
    return [t for t in tombstones if float(t.deleted_at) >= float(cutoff_ts)]


# ─────────────────────────────────────────────────────────────
# 压缩引用（B1-05：compressed references 不能复活）
# ─────────────────────────────────────────────────────────────


class CompressedVerdict(str, Enum):
    """压缩记忆受删除影响程度的判定。"""

    #: 未引用任何被删记忆
    CLEAN = "clean"
    #: 部分原始记忆被删——摘要里可能仍含被删内容
    PARTIAL = "partial"
    #: 全部原始记忆都被删
    DEAD = "dead"
    #: original_ids 无法解析，按最保守处理
    UNPARSEABLE = "unparseable"


@dataclass(frozen=True)
class CompressedAssessment:
    row_id: str = ""
    verdict: CompressedVerdict = CompressedVerdict.CLEAN
    #: 被删掉的原始 id
    removed: Tuple[int, ...] = ()
    #: 剔除被删 id 后剩下的 id
    surviving: Tuple[int, ...] = ()
    #: 是否允许注入 prompt
    injectable: bool = True

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.row_id,
            "verdict": self.verdict.value,
            "removed": list(self.removed),
            "surviving": list(self.surviving),
            "injectable": self.injectable,
        }


def parse_original_ids(raw: Any) -> Optional[List[int]]:
    """解析 `compressed_memories.original_ids`。

    它可能是 JSON 数组文本，也可能是逗号分隔字符串。
    返回 None 表示**解析不了**——调用方必须按最保守方式处理，
    而不是当成"没有引用"从而放行。
    """
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        try:
            return [int(x) for x in raw]
        except (TypeError, ValueError):
            return None
    text = str(raw).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except Exception:  # noqa: BLE001
        # 退化：按逗号/空格切分
        parts = [p for p in re.split(r"[,\s]+", text) if p]
        try:
            return [int(p) for p in parts]
        except (TypeError, ValueError):
            return None
    if isinstance(parsed, (list, tuple)):
        try:
            return [int(x) for x in parsed]
        except (TypeError, ValueError):
            return None
    return None


def assess_compressed(
    row: Mapping[str, Any],
    deleted_ids: Set[int],
    *,
    on_partial: str = "exclude",
) -> CompressedAssessment:
    """评估一条压缩记忆是否还能注入 prompt。

    默认 `on_partial="exclude"`：只要引用了任一被删记忆，
    整个摘要都不再注入。

    为什么这么激进：压缩摘要是**从原始内容生成的**，
    被删记忆的措辞、事实、隐私细节很可能已经融进摘要文本里。
    没有任何办法只"切掉那一部分"。留着 = 被删内容复活。
    """
    row_id = str(row.get("id", "") or "")
    originals = parse_original_ids(row.get("original_ids"))
    if originals is None:
        return CompressedAssessment(
            row_id=row_id,
            verdict=CompressedVerdict.UNPARSEABLE,
            injectable=False,
        )

    dead = set(int(d) for d in deleted_ids)
    removed = tuple(i for i in originals if i in dead)
    surviving = tuple(i for i in originals if i not in dead)

    if not removed:
        return CompressedAssessment(
            row_id=row_id, verdict=CompressedVerdict.CLEAN,
            surviving=tuple(originals), injectable=True,
        )

    if not surviving:
        return CompressedAssessment(
            row_id=row_id, verdict=CompressedVerdict.DEAD,
            removed=tuple(sorted(removed)), injectable=False,
        )

    return CompressedAssessment(
        row_id=row_id,
        verdict=CompressedVerdict.PARTIAL,
        removed=tuple(sorted(removed)),
        surviving=tuple(sorted(surviving)),
        injectable=(str(on_partial).lower() != "exclude"),
    )


def filter_compressed(
    rows: Iterable[Mapping[str, Any]],
    deleted_ids: Set[int],
    *,
    on_partial: str = "exclude",
) -> Tuple[List[Dict[str, Any]], List[CompressedAssessment]]:
    """剔除受删除影响的压缩记忆，并返回每条的判定（供审计/日志）。"""
    kept: List[Dict[str, Any]] = []
    verdicts: List[CompressedAssessment] = []
    for row in rows:
        verdict = assess_compressed(row, set(deleted_ids), on_partial=on_partial)
        verdicts.append(verdict)
        if verdict.injectable:
            kept.append(dict(row))
    return kept, verdicts


# ─────────────────────────────────────────────────────────────
# Embedding 版本化（B1-06）
# ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EmbeddingFingerprint:
    """一组向量的"生产条件"。

    不同 provider/model 产出的向量**不在同一个空间**，
    混在一起检索出来的相似度毫无意义——
    表现为"明明记得这件事，检索永远召不回"。
    """

    provider: str = ""
    model: str = ""
    dim: int = 0
    #: 归一化/池化等预处理约定；改了同样不可混用
    version: str = "1"

    def digest(self) -> str:
        raw = f"{self.provider}|{self.model}|{int(self.dim)}|{self.version}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "dim": int(self.dim),
            "version": self.version,
            "digest": self.digest(),
        }

    @staticmethod
    def from_dict(raw: Any) -> Optional["EmbeddingFingerprint"]:
        if not isinstance(raw, dict):
            return None
        try:
            dim = int(raw.get("dim", 0) or 0)
        except (TypeError, ValueError):
            return None
        return EmbeddingFingerprint(
            provider=str(raw.get("provider", "") or ""),
            model=str(raw.get("model", "") or ""),
            dim=dim,
            version=str(raw.get("version", "1") or "1"),
        )


def compatible(a: Optional[EmbeddingFingerprint], b: Optional[EmbeddingFingerprint]) -> bool:
    """两组向量能否混用。

    任一为空 → False。空指纹意味着"不知道这批向量怎么来的"，
    与任何东西混用都不安全。
    """
    if a is None or b is None:
        return False
    if a.digest() == b.digest():
        return True
    # digest 相同即 provider/model/dim/version 全同；
    # 走到这里说明至少一项不同 → 不可混用
    return False


@dataclass(frozen=True)
class RebuildPlan:
    """索引重建计划。"""

    required: bool = False
    reason: str = ""
    current: Optional[EmbeddingFingerprint] = None
    target: Optional[EmbeddingFingerprint] = None
    #: 是否可以后台重建（旧索引在新索引就绪前仍可用）
    background_ok: bool = True

    def as_dict(self) -> Dict[str, Any]:
        return {
            "required": self.required,
            "reason": self.reason,
            "current": self.current.to_dict() if self.current else None,
            "target": self.target.to_dict() if self.target else None,
            "background_ok": self.background_ok,
        }


def plan_rebuild(
    current: Optional[EmbeddingFingerprint],
    target: Optional[EmbeddingFingerprint],
) -> RebuildPlan:
    """判断是否需要重建向量索引。

    `current is None`（索引里没记过指纹）也要求重建：
    老索引的来源不明，继续往里加新向量等于混用。
    """
    if target is None:
        return RebuildPlan(required=False, reason="未指定目标指纹", current=current)
    if current is None:
        return RebuildPlan(
            required=True, reason="索引未记录 embedding 指纹，来源不可确认",
            target=target, background_ok=True,
        )
    if compatible(current, target):
        return RebuildPlan(required=False, reason="指纹一致", current=current, target=target)

    if current.dim != target.dim:
        reason = f"维度变化 {current.dim} → {target.dim}"
    elif current.model != target.model:
        reason = f"模型变化 {current.model!r} → {target.model!r}"
    elif current.provider != target.provider:
        reason = f"provider 变化 {current.provider!r} → {target.provider!r}"
    else:
        reason = f"预处理版本变化 {current.version!r} → {target.version!r}"

    # 维度变了必须整体重建，旧索引无法继续服务
    return RebuildPlan(
        required=True, reason=reason, current=current, target=target,
        background_ok=(current.dim == target.dim),
    )


def cache_key(
    session_id: str,
    query: str,
    fingerprint: Optional[EmbeddingFingerprint],
    *,
    memory_revision: str = "",
) -> str:
    """检索缓存键（ContextArchitecture §8）。

    必须包含 session_id、memory revision、embedding 版本、query 指纹。
    缺任何一项都会造成**跨会话或跨版本串味**：
    A 会话的缓存结果被 B 会话拿到，或者换了 embedding 模型后
    还用旧向量算出来的召回列表。
    """
    parts = [
        str(session_id or "default"),
        str(memory_revision or ""),
        fingerprint.digest() if fingerprint else "unknown",
        hashlib.sha256((query or "").encode("utf-8")).hexdigest()[:16],
    ]
    return "|".join(parts)


# ─────────────────────────────────────────────────────────────
# 索引对齐诊断（B1-04）
# ─────────────────────────────────────────────────────────────


class Issue(str, Enum):
    """索引一致性问题。低基数稳定值。

    Milvus 用 `memory_id` 作主键，SQLite 同样用 `id`，**没有中间映射表**，
    所以对齐诊断就是两个 id 集合的直接比对（B1-04）。
    """

    OK = "ok"
    #: SQLite 有行、Milvus 里没有向量 → 永远检索不到
    ORPHAN_METADATA = "orphan_metadata"
    #: Milvus 有向量、SQLite 里没有对应行 → 白占 top_k 名额
    ORPHAN_VECTOR = "orphan_vector"
    #: 向量维度与配置不符
    DIM_MISMATCH = "dim_mismatch"
    #: 两侧计数不一致
    COUNT_MISMATCH = "count_mismatch"
    #: 向量后端不可用，本次诊断不完整
    BACKEND_UNAVAILABLE = "backend_unavailable"


@dataclass(frozen=True)
class Finding:
    issue: Issue
    count: int = 0
    #: 样例 id（**只给少量**，避免把整库 id 灌进日志）
    samples: Tuple[int, ...] = ()
    action: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "issue": self.issue.value,
            "count": int(self.count),
            "samples": list(self.samples),
            "action": self.action,
        }


@dataclass(frozen=True)
class IndexHealth:
    """索引健康报告。"""

    healthy: bool = False
    findings: Tuple[Finding, ...] = ()
    rebuild_recommended: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "healthy": self.healthy,
            "rebuild_recommended": self.rebuild_recommended,
            "findings": [f.as_dict() for f in self.findings],
        }

    def counts_by_issue(self) -> Dict[str, int]:
        return {f.issue.value: f.count for f in self.findings}


_ACTIONS: Dict[Issue, str] = {
    Issue.ORPHAN_METADATA: "为这些记忆补建向量（重新 embedding 后 upsert 到 Milvus）",
    Issue.ORPHAN_VECTOR: "按 memory_id 删除 Milvus 中的孤儿向量",
    Issue.DIM_MISMATCH: "索引维度与配置不符，需整体重建 collection",
    Issue.COUNT_MISMATCH: "两侧计数不一致，按 SQLite 权威数据重建",
    Issue.BACKEND_UNAVAILABLE: "向量后端不可用，本次仅完成元数据侧诊断",
}


def _samples(ids: Iterable[int], limit: int = 5) -> Tuple[int, ...]:
    return tuple(sorted(int(i) for i in ids)[:limit])


def analyze_alignment(
    *,
    memory_ids: Iterable[int],
    vector_ids: Iterable[int] = (),
    unindexed: Iterable[int] = (),
    index_dim: int = 0,
    expected_dim: int = 0,
    backend_available: bool = True,
) -> IndexHealth:
    """比对 SQLite 元数据与 Milvus 向量。**纯函数**，输入是 id 集合。

    没有 `faiss_id_map` 之类的中间表：`memory_id` 在两侧是同一个值，
    所以"哪些记忆检索不到"就是 `mem - vec` 的差集。判定与具体库无关，
    调用方负责取 id 集合，本模块只做结论。

    `unindexed` 是写入时明确记录下来的"向量写失败"id，
    比集合差集更精确（不依赖后端能否全量列举）。
    """
    mem: Set[int] = {int(i) for i in memory_ids}
    vec: Set[int] = {int(i) for i in vector_ids}
    explicit: Set[int] = {int(i) for i in unindexed}

    findings: List[Finding] = []

    missing = (mem - vec) | (explicit & mem)
    if missing:
        findings.append(Finding(
            Issue.ORPHAN_METADATA, len(missing),
            _samples(missing), _ACTIONS[Issue.ORPHAN_METADATA],
        ))

    orphan_vec = vec - mem
    if orphan_vec:
        findings.append(Finding(
            Issue.ORPHAN_VECTOR, len(orphan_vec),
            _samples(orphan_vec), _ACTIONS[Issue.ORPHAN_VECTOR],
        ))

    if expected_dim > 0 and index_dim > 0 and int(index_dim) != int(expected_dim):
        findings.append(Finding(
            Issue.DIM_MISMATCH, 1, (),
            f"{_ACTIONS[Issue.DIM_MISMATCH]}（{index_dim} → {expected_dim}）",
        ))

    if backend_available and vec and len(mem) != len(vec):
        findings.append(Finding(
            Issue.COUNT_MISMATCH, abs(len(mem) - len(vec)), (),
            _ACTIONS[Issue.COUNT_MISMATCH],
        ))

    if not backend_available:
        findings.append(Finding(
            Issue.BACKEND_UNAVAILABLE, 1, (),
            _ACTIONS[Issue.BACKEND_UNAVAILABLE],
        ))

    rebuild = any(
        f.issue in (Issue.DIM_MISMATCH, Issue.COUNT_MISMATCH)
        for f in findings
    )
    return IndexHealth(
        healthy=not findings,
        findings=tuple(findings),
        rebuild_recommended=rebuild,
    )
