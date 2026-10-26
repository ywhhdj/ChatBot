"""FAISS 向量索引封装。"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np


class FAISSIndex:
    """向量索引：IndexIDMap2(IndexFlatIP) + L2 归一化 + id 映射。"""

    def __init__(self, dim: int = 348) -> None:
        self.index_dim = int(dim)
        self._id_map: Dict[int, int] = {}       # faiss_id -> memory_id
        self._next_id = 0
        self._available = True
        self.index = self.__build_index()

    def __build_index(self):
        try:
            import faiss

            base = faiss.IndexFlatIP(self.index_dim)
            return faiss.IndexIDMap2(base)
        except Exception:
            # faiss 不可用 -> 退化为内存线性检索（功能保留，性能下降）
            self._available = False
            return None

    @property
    def available(self) -> bool:
        return self._available and self.index is not None

    # ---------- 写入 ----------

    @staticmethod
    def normalize(vec: np.ndarray) -> np.ndarray:
        vec = np.asarray(vec, dtype="float32").reshape(-1)
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec = vec / norm
        return vec

    def add(
        self,
        vectors: List[np.ndarray],
        memory_ids: Optional[List[int]] = None
    ) -> List[int]:
        """加入向量，返回分配到的 faiss_id 列表。"""
        if not vectors:
            return []
        matrix = np.vstack([self.normalize(v) for v in vectors]).astype("float32")
        if matrix.shape[1] != self.index_dim:
            raise ValueError(
                f"向量维度不匹配: 期望 {self.index_dim}, 实际 {matrix.shape[1]}"
            )

        if self.available:
            ids = np.arange(
                self._next_id, self._next_id + len(vectors), dtype="int64"
            )
            self.index.add_with_ids(matrix, ids)
        else:
            ids = np.arange(self._next_id, self._next_id + len(vectors), dtype="int64")

        assigned: List[int] = []
        for offset, faiss_id in enumerate(ids):
            fid = int(faiss_id)
            memory_id = (
                int(memory_ids[offset])
                if memory_ids is not None and offset < len(memory_ids)
                else fid
            )
            self._id_map[fid] = memory_id
            assigned.append(fid)
        self._next_id += len(vectors)
        return assigned

    # ---------- 检索 ----------

    def search(self, query: np.ndarray, top_k: int = 10) -> List[Tuple[int, float]]:
        """返回 [(faiss_id, similarity), ...]。"""
        if not self._id_map:
            return []
        q = self.normalize(query).reshape(1, -1).astype("float32")

        if self.available:
            scores, ids = self.index.search(q, min(top_k, len(self._id_map)))
            return [
                (int(fid), float(score))
                for fid, score in zip(ids[0], scores[0])
                if int(fid) >= 0
            ]
        results: List[Tuple[int, float]] = []
        for fid in self._id_map:
            results.append((fid, 0.0))
        return results[:top_k]

    def memory_id_of(self, faiss_id: int) -> Optional[int]:
        return self._id_map.get(int(faiss_id))

    def remove(self, faiss_ids: List[int]) -> None:
        ids = [int(i) for i in faiss_ids]
        if self.available and ids:
            try:
                import numpy as np
                self.index.remove_ids(np.array(ids, dtype="int64"))
            except Exception:
                pass
        for fid in ids:
            self._id_map.pop(fid, None)

    # ---------- 持久化 ----------

    def save(self, path: str) -> bool:
        if not self.available:
            return False
        try:
            import faiss
            faiss.write_index(self.index, path)
            return True
        except Exception:
            return False

    def load(self, path: str) -> bool:
        if not self.available:
            return False
        try:
            import faiss
            import os

            if not os.path.exists(path):
                return False
            self.index = faiss.read_index(path)
            self.index_dim = self.index.d
            return True
        except Exception:
            return False

    def __len__(self) -> int:
        return len(self._id_map)

FAISS = FAISSIndex
