from dataclasses import dataclass, field
from typing import List, Dict, Any, Literal

from pydantic import BaseModel

class RAGConfig(BaseModel):
    enabled: bool = False
    doc_path: str = "./data/knowledge_base"
    sparse_weight: float = 0.3
    dense_weight: float = 0.7
    fusion_method: Literal["weighted", "rrf"] = "weighted"
    use_reranker: bool = False

@dataclass
class Document:
    id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0


@dataclass
class RetrievalResult:
    query: str
    documents: List[Document]
    total_time_ms: float = 0.0
    method: str = "hybrid"