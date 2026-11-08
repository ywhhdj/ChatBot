"""重计算内核的 Python 门面：Rust 优先、纯 Python 回退"""

from __future__ import annotations

import math
import unicodedata
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..domain import layers as _layers
from ..domain import scoring as _scoring
from ..domain import strength as _strength
from ...logger import logger

#: 单个批量上限。防止一次调用把 Rust 侧内存打满。
MAX_BATCH = 100_000


def _normalized(text: str) -> str:
    """NFKC + 小写。Rust 侧不引 unicode 归一化 crate，
    预处理必须在这一层做完，否则中英混合的 token 集合会不一致。"""
    return unicodedata.normalize("NFKC", str(text or "")).lower()


class MemoryKernel:
    """`StrengthComputer` 端口的实现。构造时自动探测 Rust 内核。"""

    def __init__(self, *, force_python: bool = False) -> None:
        self._rust: Any = None
        self._fallback_reason = ""
        self._constants_ok = False
        self._constants_diff: List[str] = []

        if force_python:
            self._fallback_reason = "forced_python"
        else:
            self._try_load_rust()

    # ---------- 探测 ----------

    def _try_load_rust(self) -> None:
        try:
            import core as _core  # type: ignore

            factory = getattr(_core, "MemoryKernel", None)
            if factory is None:
                self._fallback_reason = "core 无 MemoryKernel（内核版本过旧）"
                return
            self._rust = factory()
        except Exception as exc:  # noqa: BLE001
            self._fallback_reason = f"Rust 内核不可用: {type(exc).__name__}"
            return

        ok, diffs = self._compare_constants()
        self._constants_ok = ok
        self._constants_diff = diffs
        if not ok:
            self._fallback_reason = "常数漂移（见 constants_diff）"
            self._rust = None
            logger.warning(
                f"[MemoryKernel] Rust 与 Python 常数不一致，强制纯 Python: "
                f"{', '.join(diffs[:5])}"
            )

    def _compare_constants(self) -> Tuple[bool, List[str]]:
        try:
            import core as _core  # type: ignore

            rust = dict(_core.memory_kernel_constants()) # type: ignore
        except Exception as exc:  # noqa: BLE001
            return False, [f"读常数失败: {type(exc).__name__}"]

        expected = _layers.kernel_constants()
        diffs: List[str] = []
        for key in sorted(set(expected) | set(rust)):
            a, b = expected.get(key), rust.get(key)
            if a is None or b is None:
                diffs.append(f"缺项 {key}")
            elif not math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-12):
                diffs.append(f"{key}: py={a} rust={b}")
        return (not diffs), diffs

    # ---------- 状态 ----------

    @property
    def backend(self) -> str:
        return "rust" if self._rust is not None else "python"

    @property
    def rust_available(self) -> bool:
        return self._rust is not None

    def status(self) -> Dict[str, Any]:
        return {
            "backend": self.backend,
            "constants_ok": self._constants_ok,
            "constants_diff": list(self._constants_diff[:10]),
            "fallback_reason": self._fallback_reason,
            "embedding_backend_compiled": bool(
                getattr(self._rust, "backend_compiled", lambda: False)()
            ) if self._rust is not None else False,
        }

    # ---------- 向量 ----------

    def normalize_batch(self, vectors: Sequence[Sequence[float]]) -> List[List[float]]:
        if len(vectors) > MAX_BATCH:
            raise ValueError(f"批量超过 {MAX_BATCH} 上限")
        if self._rust is not None:
            try:
                return self._rust.normalize_batch([list(map(float, v)) for v in vectors])
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[MemoryKernel] Rust 归一化失败，降级: {type(exc).__name__}")
        out: List[List[float]] = []
        for vec in vectors:
            row = [float(x) for x in vec]
            norm = math.sqrt(sum(x * x for x in row))
            out.append([x / norm for x in row] if norm > 0 and math.isfinite(norm)
                       else [0.0] * len(row))
        return out

    def dot_batch(
        self, query: Sequence[float], matrix: Sequence[Sequence[float]]
    ) -> List[float]:
        q = [float(x) for x in query]
        if self._rust is not None:
            try:
                return self._rust.dot_batch(q, [list(map(float, r)) for r in matrix])
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[MemoryKernel] Rust 打分失败，降级: {type(exc).__name__}")
        return [
            sum(float(a) * b for a, b in zip(row, q)) if len(row) == len(q)
            else float("-inf")
            for row in matrix
        ]

    # ---------- 融合 ----------

    def rrf_fuse(
        self,
        rank_lists: Sequence[Sequence[str]],
        weights: Sequence[float],
        k: float = _scoring.RRF_K,
    ) -> List[Tuple[str, float]]:
        lists = [[str(x) for x in ranked] for ranked in rank_lists]
        ws = [float(w) for w in weights]
        if self._rust is not None:
            try:
                return [(str(a), float(b)) for a, b in
                        self._rust.rrf_fuse(lists, ws, float(k))]
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[MemoryKernel] Rust RRF 失败，降级: {type(exc).__name__}")
        # 纯 Python 回退：与 domain.scoring.rrf_fuse 的权重语义一致
        scores: Dict[str, float] = {}
        for channel, ranked in enumerate(lists):
            w = ws[channel] if channel < len(ws) else 1.0
            seen = set()
            for rank, doc_id in enumerate(ranked):
                if doc_id in seen:
                    continue
                seen.add(doc_id)
                scores[doc_id] = scores.get(doc_id, 0.0) + w / (float(k) + rank + 1)
        return sorted(scores.items(), key=lambda p: (-p[1], p[0]))

    def lexical_scores(self, query: str, documents: Sequence[str]) -> List[float]:
        q = _normalized(query)
        docs = [_normalized(d) for d in documents]
        if self._rust is not None:
            try:
                return [float(v) for v in self._rust.lexical_scores(q, docs)]
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[MemoryKernel] Rust 词法打分失败，降级: {type(exc).__name__}")
        return [_scoring.lexical_score(q, d) for d in docs]

    # ---------- 遗忘曲线 ----------

    def retention_batch(
        self,
        delta_days: Sequence[float],
        stability: Sequence[float],
        pinned: Sequence[bool],
    ) -> List[float]:
        d = [float(x) for x in delta_days]
        s = [float(x) for x in stability]
        p = [bool(x) for x in pinned]
        if self._rust is not None:
            try:
                return [float(v) for v in self._rust.retention_batch(d, s, p)]
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[MemoryKernel] Rust 保持率失败，降级: {type(exc).__name__}")
        return [
            _strength.retention(d[i], s[i], pinned=p[i] if i < len(p) else False)
            for i in range(min(len(d), len(s)))
        ]

    def initial_stability_batch(
        self,
        base_s: Sequence[float],
        s_max: Sequence[float],
        importance: Sequence[float],
        salience: Sequence[float],
    ) -> List[float]:
        if self._rust is not None:
            try:
                return [float(v) for v in self._rust.initial_stability_batch(
                    list(map(float, base_s)), list(map(float, s_max)),
                    list(map(float, importance)), list(map(float, salience)),
                )]
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[MemoryKernel] Rust S0 失败，降级: {type(exc).__name__}")
        out = []
        for i in range(min(len(base_s), len(s_max))):
            imp = float(importance[i]) if i < len(importance) else 0.0
            sal = float(salience[i]) if i < len(salience) else 0.0
            raw = float(base_s[i]) * (1.0 + _strength.IMPORTANCE_S0 * min(1, max(0, imp))) \
                * (1.0 + _strength.SALIENCE_S0 * min(1, max(0, sal)))
            out.append(min(float(s_max[i]), max(_strength.MIN_STABILITY, raw)))
        return out

    def final_scores(
        self,
        relevance: Sequence[float],
        r_eff: Sequence[float],
        floors: Sequence[float],
    ) -> List[float]:
        rel = [float(x) for x in relevance]
        r = [float(x) for x in r_eff]
        f = [float(x) for x in floors]
        if self._rust is not None:
            try:
                return [float(v) for v in self._rust.final_scores(rel, r, f)]
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[MemoryKernel] Rust 排序失败，降级: {type(exc).__name__}")
        n = min(len(rel), len(r), len(f))
        return [
            (rel[i] if rel[i] > 0 and math.isfinite(rel[i]) else 0.0)
            * (min(1, max(0, f[i])) + (1 - min(1, max(0, f[i])))
               * min(1, max(0, r[i])))
            for i in range(n)
        ]

    def jitter_batch(
        self, memory_ids: Sequence[str], day: float
    ) -> List[float]:
        ids = [str(x) for x in memory_ids]
        if self._rust is not None:
            try:
                return [float(v) for v in self._rust.jitter_batch(ids, float(day))]
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[MemoryKernel] Rust 抖动失败，降级: {type(exc).__name__}")
        return [_strength.deterministic_jitter(i, day) for i in ids]

    # ---------- Embedding 前向 ----------

    def encode_batch(self, texts: Sequence[str]) -> List[List[float]]:
        """本地 embedding 前向。**无后端时抛明确异常，不静默降级**。

        降级成 hash 向量会污染索引：fingerprint 不变但向量空间变了，
        表现为"明明记得这件事，检索永远召不回"（B1-06 最难查的场景）。
        """
        if self._rust is None:
            raise RuntimeError(
                "Rust 记忆内核不可用，无法执行本地 embedding 前向"
            )
        return [list(map(float, row)) for row in
                self._rust.encode_batch([str(t) for t in texts])]


_kernel: Optional[MemoryKernel] = None


def get_kernel(*, force_python: bool = False) -> MemoryKernel:
    """组合根用单例。"""
    global _kernel
    if _kernel is None:
        _kernel = MemoryKernel(force_python=force_python)
    return _kernel


def reset_kernel() -> None:
    """仅供测试。"""
    global _kernel
    _kernel = None
