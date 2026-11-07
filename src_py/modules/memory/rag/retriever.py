"""RAG 检索：BM25 稀疏 + 稠密内积"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, List, Optional, Sequence

from ...logger import logger
from ..compute.kernel import get_kernel
from .models import Document, RetrievalResult

#: 中文/日文无空格文本的最小切分单位
def _tokens(text: str) -> List[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    words = raw.split()
    if len(words) > 1 or all(len(w) > 3 for w in words):
        return words
    # 单段 CJK：按字符 bigram 切，兼顾召回与精度
    compact = "".join(words)
    if len(compact) <= 1:
        return [compact] if compact else []
    return [compact[i:i + 2] for i in range(len(compact) - 1)]


class BM25Retriever:
    """稀疏检索。缺 rank_bm25 时降级为确定性词频打分，不抛异常。"""

    def __init__(self, documents: List[Document]) -> None:
        self.documents = documents
        self.corpus = [doc.content for doc in documents]
        self.tokenized_corpus = [_tokens(text) for text in self.corpus]
        self.bm25 = None
        if self.tokenized_corpus:
            try:
                from rank_bm25 import BM25Okapi  # type: ignore

                self.bm25 = BM25Okapi(self.tokenized_corpus)
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"[RAG] BM25 初始化失败，用词频降级: {type(exc).__name__}")

    def _scores(self, query: str) -> List[float]:
        q = _tokens(query)
        if self.bm25 is not None:
            try:
                return [float(x) for x in self.bm25.get_scores(q)]
            except Exception:  # noqa: BLE001
                pass
        # 确定性降级：查询 token 在文档里的命中比例
        qset = set(q)
        out = []
        for tokens in self.tokenized_corpus:
            if not qset or not tokens:
                out.append(0.0)
                continue
            hits = sum(1 for t in tokens if t in qset)
            out.append(hits / max(1, len(tokens)))
        return out

    def retrieve(self, query: str, top_k: int = 5) -> RetrievalResult:
        started = time.time()
        if not self.documents:
            return RetrievalResult(query=query, documents=[], total_time_ms=0.0,
                                   method="bm25")
        scores = self._scores(query)
        indices = sorted(
            range(len(scores)), key=lambda i: scores[i], reverse=True
        )[:max(1, int(top_k))]
        docs = []
        for idx in indices:
            doc = self.documents[idx]
            doc.score = float(scores[idx])
            docs.append(doc)
        return RetrievalResult(
            query=query, documents=docs,
            total_time_ms=(time.time() - started) * 1000.0, method="bm25",
        )


def _encode_sync(
    texts: Sequence[str], embed_fn: Optional[Callable[[List[str]], Any]]
) -> List[List[float]]:
    """**同步**编码。调用方必须保证当前线程没有运行中的 loop。"""
    if embed_fn is None:
        from ..utils import embed_texts_sync

        rows = embed_texts_sync(list(texts))
    else:
        rows = embed_fn(list(texts))
        if asyncio.iscoroutine(rows) or isinstance(rows, asyncio.Future):
            raise RuntimeError(
                "同步检索不能接收异步 embed_fn，请改用 await retrieve_async()"
            )
    return [[float(x) for x in list(row)] for row in (rows or [])]


class DenseRetriever:
    """稠密检索：批量内积（Rust kernel 优先）。

    `retrieve()` 是**同步**方法，用于离线回放与非异步上下文；
    `retrieve_async()` 把整段计算 offload 到线程池，避免阻塞 Web loop。
    """

    def __init__(
        self,
        documents: List[Document],
        embed_fn: Optional[Callable[[List[str]], Any]] = None,
    ) -> None:
        self.documents = documents
        self.embed_fn = embed_fn
        self.embeddings: List[List[float]] = []
        self.kernel = get_kernel()
        if documents:
            self._build_index()

    def _build_index(self) -> None:
        texts = [doc.content for doc in self.documents]
        encoded = _encode_sync(texts, self.embed_fn)
        self.embeddings = self.kernel.normalize_batch(encoded)

    def _score(self, query: str) -> List[float]:
        q = _encode_sync([query], self.embed_fn)
        if not q:
            return [0.0] * len(self.documents)
        query_vec = self.kernel.normalize_batch([q[0]])[0]
        return list(self.kernel.dot_batch(query_vec, self.embeddings))

    def retrieve(self, query: str, top_k: int = 5) -> RetrievalResult:
        started = time.time()
        if not self.documents or not self.embeddings:
            return RetrievalResult(query=query, documents=[], total_time_ms=0.0,
                                   method="dense")
        scores = self._score(query)
        indices = sorted(
            range(len(scores)), key=lambda i: scores[i], reverse=True
        )[:max(1, int(top_k))]
        docs = []
        for idx in indices:
            doc = self.documents[idx]
            doc.score = float(scores[idx])
            docs.append(doc)
        return RetrievalResult(
            query=query, documents=docs,
            total_time_ms=(time.time() - started) * 1000.0, method="dense",
        )

    async def retrieve_async(self, query: str, top_k: int = 5) -> RetrievalResult:
        """把批量内积放到线程池，不在协程里阻塞事件循环。"""
        return await asyncio.to_thread(self.retrieve, query, top_k)
