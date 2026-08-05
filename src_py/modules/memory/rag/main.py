from typing import Callable, List, Optional
from .models import Document, RetrievalResult
import time

class HybridRetriever:
    """
    混合检索：BM25 + Dense，支持分数融合（加权平均或 Reciprocal Rank Fusion）。
    可选挂载 Cross-Encoder Reranker 进行精排。
    """
    def __init__(
        self,
        documents: List[Document],
        sparse_weight: float = 0.3,
        dense_weight: float = 0.7,
        fusion_method: str = "weighted",  # "weighted" or "rrf"
        reranker: Optional[Callable[[str, List[Document]], List[Document]]] = None,
    ):
        from .retriever import BM25Retriever, DenseRetriever
        self.sparse = BM25Retriever(documents)
        self.dense = DenseRetriever(documents)
        from .models import RAGConfig
        self.config=RAGConfig(
            enabled=True,
            doc_path="./data/knowledge_base",
            sparse_weight=sparse_weight,
            dense_weight=dense_weight,
            fusion_method=fusion_method,
            use_reranker=False
        )
        self.reranker = reranker
        from .store import DocumentStore
        self.doc_store = DocumentStore()
    
    def _load_documents(self, path: str):
        from pathlib import Path
        p = Path(path)
        if not p.exists():
            return
        docs = []
        for file in p.rglob("*"):
            if file.suffix in (".txt", ".md"):
                content = file.read_text(encoding="utf-8")
                doc = Document(
                    id=str(file.relative_to(p)),
                    content=content,
                    metadata={"source": str(file)}
                )
                docs.append(doc)
        self.doc_store.add_documents(docs)
        self.doc_store.save()

    def retrieve(
            self, query: str, top_k: int = 5,
            rerank_top_k: int = 15
        ) -> RetrievalResult:
        start = time.time()

        # 1. 分别检索更多候选（便于融合）
        sparse_result = self.sparse.retrieve(query, top_k=rerank_top_k)
        dense_result = self.dense.retrieve(query, top_k=rerank_top_k)

        # 2. 融合分数
        fused = self.__fusion(sparse_result.documents, dense_result.documents)

        # 3. 可选重排序
        if self.reranker and len(fused) > top_k:
            fused = self.reranker(query, fused)

        # 4. 截断 top_k
        fused = fused[:top_k]

        elapsed = (time.time() - start) * 1000
        return RetrievalResult(query=query, documents=fused, total_time_ms=elapsed, method="hybrid")

    def __fusion(self, sparse_docs: List[Document], dense_docs: List[Document]) -> List[Document]:
        """分数融合：加权平均或 RRF"""
        doc_map = {}
        if self.config.fusion_method == "weighted":
            for doc in sparse_docs:
                doc_map[doc.id] = {"doc": doc, "score": doc.score * self.config.sparse_weight}
            for doc in dense_docs:
                if doc.id in doc_map:
                    doc_map[doc.id]["score"] += doc.score * self.config.dense_weight
                else:
                    doc_map[doc.id] = {
                        "doc": doc,
                        "score": doc.score * self.config.dense_weight
                    }
        elif self.config.fusion_method == "rrf":
            # Reciprocal Rank Fusion
            k = 60
            for rank, doc in enumerate(sparse_docs):
                doc_map[doc.id] = {
                    "doc": doc, 
                    "score": 1.0 / (k + rank)
                }
            for rank, doc in enumerate(dense_docs):
                if doc.id in doc_map:
                    doc_map[doc.id]["score"] += 1.0 / (k + rank)
                else:
                    doc_map[doc.id] = {
                        "doc": doc,
                        "score": 1.0 / (k + rank)
                    }
        else:
            raise ValueError(f"Unknown fusion method: {self.config.fusion_method}")

        # 按融合后分数降序排列
        sorted_items = sorted(doc_map.values(), key=lambda x: x["score"], reverse=True)
        for item in sorted_items:
            item["doc"].score = item["score"]
        return [item["doc"] for item in sorted_items]