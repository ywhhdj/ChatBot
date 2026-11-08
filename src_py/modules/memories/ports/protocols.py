"""记忆领域的端口（Protocol）定义。

对应 `OptimizationPlan.md` L1-02："定义端口：ContextStore、Clock、
AuditSink"，以及 M1-01 的 `MemoryClock`。

**端口属于领域层，不属于适配器层**：它由"领域需要什么"决定，
不是"某个库能提供什么"。所有实现（Rust / Milvus / SQLite）
单向依赖这里，绝不反向。

为什么用 `typing.Protocol` 而不是 ABC
──────────────────────────────────
适配器来自不同世界：pymilvus 的 MilvusClient、进程内分桶实现、
Rust 的 PyO3 对象。要求它们继承同一个基类等于强迫改写第三方类型。
Protocol 做结构化匹配，测试里塞个假实现就能跑全流程。
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple, runtime_checkable

from ..domain.layers import MemoryLayer


# ─────────────────────────────────────────────────────────────
# 时钟
# ─────────────────────────────────────────────────────────────


@runtime_checkable
class MemoryClock(Protocol):
    """记忆时间轴。M1-01：三种时钟 wall / active / game。

    单位约定（**不能混**）：
    * `now_seconds()` —— epoch 秒，用于 10 分钟突击窗口判定；
    * `now_day()` —— 自 epoch 起的天数（可含小数），用于 R(Δ,S)。
    """

    def now_seconds(self) -> float: ...

    def now_day(self) -> float: ...

    def kind(self) -> str: ...


# ─────────────────────────────────────────────────────────────
# 向量存储
# ─────────────────────────────────────────────────────────────


@runtime_checkable
class VectorStore(Protocol):
    """向量索引端口。Milvus / 进程内实现都满足它。

    **scope 过滤必须在存储查询阶段完成**，不能返回全局 top-K 再过滤
    （SecurityAndAuditDesign §7）。所有 search 都强制带 `session_id`。
    """

    name: str

    def ensure_ready(self, *, dim: int, fingerprint: str) -> None:
        """建 collection / 校验维度与 embedding 指纹。

        指纹不一致时**只告警不自动重建**（B1-06）：重建可能耗时很久，
        自动执行会在启动时卡死进程。结论暴露给界面由用户决定。
        """
        ...

    def add(
        self,
        memory_ids: Sequence[int],
        vectors: Sequence[Sequence[float]],
        *,
        session_id: str,
        layer: MemoryLayer,
        fingerprint: str,
    ) -> None: ...

    def search(
        self,
        query_vector: Sequence[float],
        *,
        session_id: str,
        layers: Sequence[MemoryLayer],
        top_k: int,
        fingerprint: str,
    ) -> List[Tuple[int, float]]:
        """返回 `[(memory_id, score)]`，已按分数降序、已过滤 scope。"""
        ...

    def remove(self, memory_ids: Sequence[int], *, session_id: str) -> None: ...

    def list_ids(self, *, session_id: str = "", limit: int = 200_000) -> List[int]:
        """列出已索引的 memory_id（对齐诊断用）。"""
        ...

    def flush(self) -> None: ...

    def stats(self) -> Dict[str, Any]: ...


# ─────────────────────────────────────────────────────────────
# Embedding / 计算
# ─────────────────────────────────────────────────────────────


@runtime_checkable
class EmbeddingBackend(Protocol):
    """把文本变成向量的端口。Rust kernel / ONNX / HTTP 都可实现。"""

    @property
    def fingerprint(self) -> str: ...

    @property
    def dim(self) -> int: ...

    def encode(self, texts: Sequence[str]) -> List[List[float]]: ...


@runtime_checkable
class StrengthComputer(Protocol):
    """批量数值计算端口。Rust kernel 实现，纯 Python 实现做回退。"""

    def retention_batch(
        self, delta_days: Sequence[float], stability: Sequence[float], pinned: Sequence[bool]
    ) -> List[float]: ...

    def final_scores(
        self,
        relevance: Sequence[float],
        r_eff: Sequence[float],
        floors: Sequence[float],
    ) -> List[float]: ...

    def rrf_fuse(
        self,
        rank_lists: Sequence[Sequence[str]],
        weights: Sequence[float],
        k: float,
    ) -> List[Tuple[str, float]]: ...

    def normalize_batch(self, vectors: Sequence[Sequence[float]]) -> List[List[float]]: ...

    def dot_batch(
        self, query: Sequence[float], matrix: Sequence[Sequence[float]]
    ) -> List[float]: ...


# ─────────────────────────────────────────────────────────────
# 使用事件写入
# ─────────────────────────────────────────────────────────────


@runtime_checkable
class UsageSink(Protocol):
    """`MemoryUsageEvent` 的持久化端口（M1-04）。"""

    def write(self, events: Sequence[Mapping[str, Any]]) -> int: ...
