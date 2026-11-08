from math import e
from typing import Literal, Optional, Union

def create_adapter(
    provider:str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    **kwargs,
    
):
    if provider == "sentence":
        from .adapters import SentenceEmbeddingAdapter
        return SentenceEmbeddingAdapter(
            model_path=model or "all-MiniLM-L6-v2",
            **kwargs
        )
    elif provider == "openai":
        from .adapters import OpenAIEmbeddingAdapter
        return OpenAIEmbeddingAdapter(
            model=model or "text-embedding-3-small",
            api_key=api_key or "",
            **kwargs
        )
    elif provider == "ollama":
        from .adapters import OllamaEmbeddingAdapter
        return OllamaEmbeddingAdapter(
            model=model or "nomic-embed-text",
            **kwargs
        )
    
    else:
        raise ValueError(f"不支持的提供商: {provider}")