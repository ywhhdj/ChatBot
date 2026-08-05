from typing import List

from .models import Document, RetrievalResult
import time

class BM25Retriever:
    def __init__(self, documents: List[Document]):
        self.corpus = [doc.content for doc in documents]
        self.documents = documents
        self.tokenized_corpus = [doc.split() for doc in self.corpus]
        from rank_bm25 import BM25Okapi  # type: ignore
        self.bm25 = BM25Okapi(self.tokenized_corpus)

    def retrieve(self, query: str, top_k: int = 5) -> RetrievalResult:
        start = time.time()
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
        return RetrievalResult(query=query, documents=docs, total_time_ms=elapsed, method="bm25")

import numpy as np
from typing import List
import faiss
from .models import Document, RetrievalResult
import time


class DenseRetriever:
    def __init__(self, documents: List[Document]):
        self.documents = documents
        self.embeddings = None
        self.index = None
        self._build_index()

    def _build_index(self):
        texts = [doc.content for doc in self.documents]
        self.embeddings = self.model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
        dim = self.embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dim)  # 内积（cosine 近似）
        self.index.add(self.embeddings.astype(np.float32))

    def retrieve(self, query: str, top_k: int = 5) -> RetrievalResult:
        start = time.time()
        query_vec = self.model.encode([query], normalize_embeddings=True)
        scores, indices = self.index.search(query_vec.astype(np.float32), top_k)
        docs = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.documents):
                continue
            doc = self.documents[idx]
            doc.score = float(score)
            docs.append(doc)
        elapsed = (time.time() - start) * 1000
        return RetrievalResult(query=query, documents=docs, total_time_ms=elapsed, method="dense")