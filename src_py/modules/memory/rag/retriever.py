import asyncio
import time
from typing import Any, Callable, List, Optional

import numpy as np

from ...logger import logger
from .models import Document, RetrievalResult


async def _await_coro(coro):
    return await coro

class BM25Retriever:
    def __init__(self, documents: List[Document]):
        self.corpus = [doc.content for doc in documents]
        self.documents = documents
        self.tokenized_corpus = [doc.split() for doc in self.corpus]
        self.bm25 = None
        if self.tokenized_corpus:
            try:
                from rank_bm25 import BM25Okapi  # type: ignore

                self.bm25 = BM25Okapi(self.tokenized_corpus)
            except Exception as exc:
                logger.warning(f"[RAG] BM25 初始化失败，稀疏检索降级: {exc}")
                self.bm25 = None

    def retrieve(self, query: str, top_k: int = 5) -> RetrievalResult:
        start = time.time()
        if self.bm25 is None or not self.documents:
            return RetrievalResult(
                query=query,
                documents=[],
                total_time_ms=0.0,
                method="bm25"
            )
        tokenized_query = query.split()
        scores = self.bm25.get_scores(tokenized_query)
        # 取 top_k
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        docs = []
        for idx in top_indices:
            doc = self.documents[idx]
            doc.score = float(scores[idx])
            docs.append(doc)
        elapsed = (time.time() - start) * 1000
        return RetrievalResult(
            query=query,
            documents=docs,
            total_time_ms=elapsed,
            method="bm25"
        )

import numpy as np
from typing import List
import faiss
from .models import Document, RetrievalResult
import time


class DenseRetriever:
    """密集检索。

    改为接收一个 embed_fn（与记忆系统同一套嵌入接口），
    既支持同步函数也支持协程（内部用一次性 loop 跑完）。
    """

    def __init__(
        self,
        documents: List[Document],
        embed_fn: Optional[Callable[[List[str]], Any]] = None,
    ):
        self.documents = documents
        self.embed_fn = embed_fn
        self.embeddings = None
        self.index = None
        self._build_index()

    def _encode(self, texts: List[str]) -> np.ndarray:
        if self.embed_fn is None:
            from ..utils import embed_texts_sync
            return embed_texts_sync(texts)
        result = self.embed_fn(texts)
        if asyncio.iscoroutine(result) or isinstance(result, asyncio.Future):
            result = asyncio.run(_await_coro(result))
        return np.asarray(result, dtype=np.float32)

    def _build_index(self):
        if not self.documents:
            self.embeddings = np.empty((0, 0), dtype=np.float32)
            self.index = None
            return
        texts = [doc.content for doc in self.documents]
        self.embeddings = self._encode(texts)
        if self.embeddings.ndim == 1:
            self.embeddings = self.embeddings.reshape(1, -1)
        dim = self.embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dim)  # 内积（cosine 近似）
        self.index.add(self.embeddings.astype(np.float32))

    def retrieve(self, query: str, top_k: int = 5) -> RetrievalResult:
        start = time.time()
        if self.index is None or self.index.ntotal == 0:
            return RetrievalResult(
                query=query,
                documents=[],
                total_time_ms=0.0,
                method="dense"
            )
        query_vec = self._encode([query])
        # C166：同上，faiss Python 接口 search 只接受 2 个参数
        scores, indices = self.index.search(query_vec.astype(np.float32), top_k)
        docs = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.documents):
                continue
            doc = self.documents[idx]
            doc.score = float(score)
            docs.append(doc)
        elapsed = (time.time() - start) * 1000
        return RetrievalResult(
            query=query,
            documents=docs,
            total_time_ms=elapsed,
            method="dense"
        )