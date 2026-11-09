"""本地性能基线 harness（B2-06 / `BackendPlan.md` §7）。

依据 `OptimizationPlan.md` §10「先测量再优化」与
`docs/README.md` §4.10："缓存、RRF、reranker、批量 embedding 和新的
索引都要有基线和回滚开关"。

这个模块提供**可复测的测量框架**，不产出"性能已达标"结论：
* 用 `tracemalloc` 测峰值内存（标准库，不引依赖）；
* 用 `time.perf_counter` 测冷/暖 P50/P95；
* 同一份合成输入可在 `rust` / `python` 两个 kernel 后端上跑，
  差异写进 `comparison`，供"是否值得下沉"的决策使用；
* 结果**必须标注 synthetic=True**，合成数据不能代表真实语料。

为什么不直接计时一次就下结论
──────────────────────────
单次计时受 GC、热量、调度器抢占影响，方差大到能得出任意结论。
这里每个规模跑 `repeats` 次，丢弃第一次（冷启动），
报告 P50/P95 与吞吐，且把"冷"单独列出来。
"""

from __future__ import annotations

import time
import tracemalloc
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import metrics as M

#: 默认测量规模（候选条数）
DEFAULT_SIZES: Tuple[int, ...] = (100, 1000, 5000)
DEFAULT_REPEATS = 5
DEFAULT_DIM = 384


@dataclass
class BenchPoint:
    operation: str = ""
    size: int = 0
    backend: str = ""
    cold_ms: float = 0.0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    throughput_per_sec: float = 0.0
    peak_bytes: int = 0
    repeats: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "operation": self.operation,
            "size": self.size,
            "backend": self.backend,
            "cold_ms": round(self.cold_ms, 3),
            "p50_ms": round(self.p50_ms, 3),
            "p95_ms": round(self.p95_ms, 3),
            "throughput_per_sec": round(self.throughput_per_sec, 1),
            "peak_bytes": self.peak_bytes,
            "repeats": self.repeats,
        }


@dataclass
class BenchReport:
    synthetic: bool = True
    dim: int = DEFAULT_DIM
    repeats: int = DEFAULT_REPEATS
    points: List[BenchPoint] = field(default_factory=list)
    comparison: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    queue_depth: Dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "synthetic": self.synthetic,
            "dim": self.dim,
            "repeats": self.repeats,
            "points": [p.as_dict() for p in self.points],
            "comparison": dict(self.comparison),
            "warnings": list(self.warnings),
            "queue_depth": dict(self.queue_depth),
        }


def _vectors(n: int, dim: int) -> List[List[float]]:
    """确定性合成向量。不用随机数：两次运行输入必须完全一致。"""
    return [
        [float(((i + j) % 17) - 8) / 8.0 for j in range(dim)]
        for i in range(n)
    ]


def _rank_lists(n: int, channels: int = 5) -> List[List[str]]:
    return [
        [f"m{(i + c) % max(1, n)}" for i in range(n)]
        for c in range(channels)
    ]


def _measure(fn, repeats: int) -> Tuple[float, List[float], int]:
    """返回 `(冷启动耗时, 暖耗时列表, 峰值内存字节)`。"""
    tracemalloc.start()
    try:
        t0 = time.perf_counter()
        fn()
        cold = (time.perf_counter() - t0) * 1000.0
        warm: List[float] = []
        for _ in range(repeats):
            t0 = time.perf_counter()
            fn()
            warm.append((time.perf_counter() - t0) * 1000.0)
        _current, peak = tracemalloc.get_traced_memory()
        return cold, warm, int(peak)
    finally:
        tracemalloc.stop()


def benchmark_kernel(
    kernel: Any,
    *,
    sizes: Sequence[int] = DEFAULT_SIZES,
    dim: int = DEFAULT_DIM,
    repeats: int = DEFAULT_REPEATS,
    queue_depth: Optional[Dict[str, int]] = None,
) -> BenchReport:
    """测一个 `MemoryKernel`（Rust 或纯 Python 回退）。

    只测**重计算路径**：归一化、批量打分、RRF、强度排序。
    不测网络/磁盘 —— 那些属于部署环境，不该混进内核基线。
    """
    report = BenchReport(
        synthetic=True, dim=int(dim), repeats=int(repeats),
        queue_depth=dict(queue_depth or {}),
    )
    status = kernel.status() if hasattr(kernel, "status") else {}
    backend = str(status.get("backend", "unknown"))
    report.warnings.append(
        "合成数据基线，仅用于比较两个 kernel 后端；不得据此宣称线上性能"
    )
    if status.get("fallback_reason"):
        report.warnings.append(
            f"当前后端有降级原因: {status['fallback_reason']}"
        )

    for n in sizes:
        n = max(1, int(n))
        vectors = _vectors(n, dim)
        query = vectors[0]
        ranks = _rank_lists(n)
        weights = [1.0] * len(ranks)
        rel = [1.0] * n
        r = [0.5] * n
        floors = [0.2] * n

        operations: List[Tuple[str, Any]] = [
            ("normalize_batch", lambda: kernel.normalize_batch(vectors)),
            ("dot_batch", lambda: kernel.dot_batch(query, vectors)),
            ("rrf_fuse", lambda: kernel.rrf_fuse(ranks, weights, 60.0)),
            ("final_scores", lambda: kernel.final_scores(rel, r, floors)),
        ]
        for name, fn in operations:
            try:
                cold, warm, peak = _measure(fn, max(1, int(repeats)))
            except Exception as exc:  # noqa: BLE001
                report.warnings.append(
                    f"{name}@{n} 失败: {type(exc).__name__}"
                )
                continue
            p50 = M.percentile(warm, 0.50)
            report.points.append(BenchPoint(
                operation=name, size=n, backend=backend,
                cold_ms=cold, p50_ms=p50, p95_ms=M.percentile(warm, 0.95),
                throughput_per_sec=(n / (p50 / 1000.0)) if p50 > 0 else 0.0,
                peak_bytes=peak, repeats=len(warm),
            ))
    return report


def compare_backends(
    rust_report: BenchReport,
    python_report: BenchReport,
) -> Dict[str, Any]:
    """对照两个后端。**只给差异，不下'应该用哪个'的结论**。"""
    py_index = {
        (p.operation, p.size): p.p50_ms for p in python_report.points
    }
    rows: List[Dict[str, Any]] = []
    for point in rust_report.points:
        baseline = py_index.get((point.operation, point.size))
        if baseline is None or baseline <= 0:
            continue
        rows.append({
            "operation": point.operation,
            "size": point.size,
            "python_p50_ms": round(baseline, 3),
            "rust_p50_ms": round(point.p50_ms, 3),
            "speedup": round(baseline / point.p50_ms, 3)
            if point.p50_ms > 0 else None,
        })
    return {
        "rows": rows,
        "note": "合成数据对照；上线前须用真实语料与部署环境复测",
    }
