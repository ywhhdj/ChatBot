import json
import os
from pathlib import Path
from typing import List, Optional, Dict
from .models import Document


class DocumentStore:
    """
    文档存储：支持从本地文件加载、增量添加、持久化。
    每个文档有一个唯一 ID 和原始内容。
    """
    def __init__(self, storage_path: str = "./data/rag_docs.json"):
        self.storage_path = Path(storage_path)
        self.documents: Dict[str, Document] = {}
        self._load()

    def _load(self):
        if self.storage_path.exists():
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data:
                    doc = Document(**item)
                    self.documents[doc.id] = doc

    def save(self):
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump([doc.__dict__ for doc in self.documents.values()], f, ensure_ascii=False, indent=2)

    def add_document(self, doc: Document):
        self.documents[doc.id] = doc

    def add_documents(self, docs: List[Document]):
        for doc in docs:
            self.documents[doc.id] = doc

    def get_all(self) -> List[Document]:
        return list(self.documents.values())

    def get_by_ids(self, ids: List[str]) -> List[Document]:
        return [self.documents[i] for i in ids if i in self.documents]

    def clear(self):
        self.documents.clear()