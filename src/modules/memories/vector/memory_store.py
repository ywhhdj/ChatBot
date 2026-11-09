"""进程内向量实现"""

from __future__ import annotations

import math
import threading
from typing import Any, Dict, List, Sequence, Tuple

from ..domain.layers import MemoryLayer
from .models import VectorStoreConfig


class InMemoryVectorStore:
    name = "memory"

    def __init__(self, config: VectorStoreConfig) -> None:
        self.config = config
        self._lock = threading.RLock()
        self._dim = 0
        self._fingerprint = ""
        self._ready = False
        #: (session_id, layer) -> [(memory_id, vector, fingerprint)]
        self._buckets: Dict[Tuple[str, str], List[Tuple[int, List[float], str]]] = {}

    @property
    def available(self) -> bool:
        return True

    def ensure_ready(self, *, dim: int, fingerprint: str) -> None:
        self._dim = int(dim)
        self._fingerprint = str(fingerprint)
        self._ready = True

    def add(
        self,
        memory_ids: Sequence[int],
        vectors: Sequence[Sequence[float]],
        *,
        session_id: str,
        layer: MemoryLayer,
        fingerprint: str,
    ) -> None:
        if len(memory_ids) != len(vectors):
            raise ValueError("memory_ids 与 vectors 长度不一致")
        key = (str(session_id), str(getattr(layer, "value", layer)))
        sid = str(session_id)
        fp = str(fingerprint)
        with self._lock:
            bucket = self._buckets.setdefault(key, [])
            # 先清掉同 id 的旧向量
            bucket[:] = [row for row in bucket if row[0] not in set(int(i) for i in memory_ids)]
            for mid, vec in zip(memory_ids, vectors):
                if len(vec) != self._dim:
                    raise ValueError("向量维度不匹配")
                n = math.sqrt(sum(float(x) ** 2 for x in vec)) or 1.0
                bucket.append((int(mid), [float(x) / n for x in vec], fp))

    def search(
        self,
        query_vector: Sequence[float],
        *,
        session_id: str,
        layers: Sequence[MemoryLayer],
        top_k: int,
        fingerprint: str,
    ) -> List[Tuple[int, float]]:
        if not self._ready:
            raise RuntimeError("ensure_ready() 尚未调用")
        n = math.sqrt(sum(float(x) ** 2 for x in query_vector)) or 1.0
        q = [float(x) / n for x in query_vector]
        k = max(1, min(int(top_k), int(self.config.max_top_k)))
        fp = str(fingerprint)
        scored: List[Tuple[int, float]] = []
        with self._lock:
            for layer in layers or []:
                key = (str(session_id), str(getattr(layer, "value", layer)))
                for mid, vec, stored_fp in self._buckets.get(key, []):
                    if stored_fp != fp or len(vec) != len(q):
                        continue
                    scored.append((mid, sum(a * b for a, b in zip(q, vec))))
        scored.sort(key=lambda p: p[1], reverse=True)
        # 同一个 memory_id 可能跨层重复，去重保留最高分
        seen = set()
        out: List[Tuple[int, float]] = []
        for mid, score in scored:
            if mid in seen:
                continue
            seen.add(mid)
            out.append((mid, score))
            if len(out) >= k:
                break
        return out

    def remove(self, memory_ids: Sequence[int], *, session_id: str = "") -> None:
        targets = set()
        for raw in memory_ids:
            try:
                targets.add(int(raw))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
        with self._lock:
            for key, bucket in self._buckets.items():
                if session_id and key[0] != str(session_id):
                    continue
                bucket[:] = [row for row in bucket if row[0] not in targets]

    def list_ids(self, *, session_id: str = "", limit: int = 200_000) -> List[int]:
        with self._lock:
            ids = {
                int(mid)
                for (sid, _layer), bucket in self._buckets.items()
                if not session_id or sid == str(session_id)
                for mid, _vec, _fp in bucket
            }
        return sorted(ids)[: int(limit)]

    def flush(self) -> None:
        return

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "backend": self.name,
                "available": True,
                "ready": self._ready,
                "dim": self._dim,
                "buckets": len(self._buckets),
                "entries": sum(len(b) for b in self._buckets.values()),
                "degraded": True,
                **self.config.as_dict(),
            }
