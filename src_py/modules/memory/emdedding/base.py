from abc import ABC, abstractmethod
import asyncio
from types import CoroutineType
from typing import Optional, Union
from numpy import ndarray
from abc import ABC, abstractmethod
import asyncio
from typing import Any, Dict, Optional, Union, List
from numpy import ndarray,vstack,vstack
from ...logger import logger

EmbeddingResult = Union[ndarray, List[ndarray]]

class _BaseEmbeddingAdapter(ABC):
    def __init__(
            self,
            model: str,
            normalize: bool = True,
            device: Optional[str] = None,
            batch_size: int = 32,
            max_retries: int = 3
        ):
            self.model_name = model
            self.normalize = normalize
            self.device = device
            self.batch_size = batch_size
            self.max_retries = max_retries
            self._model = None
            self._initialized = False
            self._params = {
                "model": model,
                "normalize_embeddings": normalize
            }
    @abstractmethod
    def init_model(self) -> None:
        pass
    
    @abstractmethod
    def embed(self, texts: Union[str, List[str]]) -> EmbeddingResult:
        pass
    
    def embed_batch(
        self, 
        texts: List[str], 
        return_as_list: bool = True
    ) -> Union[List[ndarray], ndarray]:
        """批量嵌入文本（同步）"""
        if not texts:
            raise ValueError("文本列表不能为空")
        
        if len(texts) == 1:
            result = self.embed(texts[0])
            if isinstance(result, ndarray) and not return_as_list:
                return result
            return [result] if isinstance(result, ndarray) else result
        
        # 分批处理
        all_embeddings: List[ndarray] = []
        
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            try:
                batch_result = self.embed(batch)
                if isinstance(batch_result, ndarray):
                    all_embeddings.extend([batch_result])
                else:
                    all_embeddings.extend(batch_result)
            except Exception as e:
                logger.error(f"批处理嵌入失败 (索引 {i}-{i+len(batch)-1}): {e}")
                raise
        
        if not return_as_list and all_embeddings:
            return vstack(all_embeddings)
        
        return all_embeddings

    def get_params(self) -> Dict[str, Any]:
        return self._params.copy()
    
    def close(self) -> None:
        self._model = None
        self._initialized = False
    
    def __str__(self) -> str:
        return f"{self.__class__.__name__}(model={self.model_name})"

class _AsyncEmbeddingAdapter(_BaseEmbeddingAdapter):

    def __init__(
        self,
        model: str,
        device: Optional[str] = None,
        normalize: bool = True,
        batch_size: int = 32,
        max_retries: int = 3
    ):
        super().__init__(model, normalize, device, batch_size, max_retries)
    
    @abstractmethod
    def embed(self, texts: Union[str, List[str]]) -> CoroutineType[Any, Any, EmbeddingResult]:
        pass

    async def close(self):
        if self.__model:
            await self.__model.aclose() # type: ignore
            self.__model = None
        super().close()
    
    async def embed_batch(
        self, 
        texts: List[str], 
        return_as_list: bool = True
    ) -> Union[List[ndarray], ndarray]:
        """异步批量嵌入文本"""
        if not texts:
            raise ValueError("文本列表不能为空")
        
        if len(texts) == 1:
            result = await self.embed(texts[0])
            if isinstance(result, ndarray) and not return_as_list:
                return result
            return [result] if isinstance(result, ndarray) else result
        # 异步分批处理
        all_embeddings: List[ndarray] = []
        
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            try:
                batch_result = await self.embed(batch)
                if isinstance(batch_result, ndarray):
                    all_embeddings.extend([batch_result])
                else:
                    all_embeddings.extend(batch_result)
            except Exception as e:
                logger.error(f"异步批处理嵌入失败 (索引 {i}-{i+len(batch)-1}): {e}")
                raise
        if not return_as_list and all_embeddings:
            return vstack(all_embeddings)
        return all_embeddings
