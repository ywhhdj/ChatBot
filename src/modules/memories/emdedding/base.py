from abc import ABC, abstractmethod
import asyncio
from types import CoroutineType
from typing import Optional, Union
from numpy import ndarray
from abc import ABC, abstractmethod
import asyncio
from typing import Any, Dict, Optional, Union, List
from numpy import ndarray, vstack
from ...logger import logger

EmbeddingResult = Union[ndarray, List[ndarray]]

class BaseEmbeddingAdapter(ABC):
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

class AsyncEmbeddingAdapter(BaseEmbeddingAdapter):

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
        """C160：原实现 `if self.__model:` —— 双重错误。

        1. `__model` 出现在 `_AsyncEmbeddingAdapter` 类体内，
           被 name mangling 成 `_AsyncEmbeddingAdapter__model`；
        2. 真正的属性叫 `self._model`，`__model` 从未被赋值过。

        于是 `close()` 一调用就 AttributeError，模型资源永远不释放。
        """
        model = getattr(self, "_model", None)
        if model is not None:
            aclose = getattr(model, "aclose", None)
            if aclose is not None:
                try:
                    result = aclose()
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as exc:
                    logger.debug(f"关闭 embedding 模型失败: {exc}")
            self._model = None
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
