import asyncio
import os
from re import S
from typing import List, Optional, Union
from numpy import array,float32, ndarray,linalg

from ...utils import decorators
from ...logger import logger
from .base import AsyncEmbeddingAdapter
from ...runtime import RuntimePath


EmbeddingResult = Union[ndarray, List[ndarray]]

class EmbeddingError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        logger.exception(message)

class SentenceEmbeddingAdapter(AsyncEmbeddingAdapter):
    def __init__(
        self,
        model_path: Optional[str] = None,
        normalize: bool = True,
        device: Optional[str] = None,
        batch_size: int = 32,
        max_retries: int = 3,
        thread_pool_size: int = 4
    ):
        if model_path is None:
            model_path = str(RuntimePath.get_models_path(
                "emotion/model_quint8_avx2.onnx"
            ))
        super().__init__(
            model=model_path,
            normalize=normalize,
            device=device,
            batch_size=batch_size,
            max_retries=max_retries
        )
        if device is None:
            try:
                from torch import cuda
                self.device = "cuda" if cuda.is_available() else "cpu"
            except ImportError:
                self.device = "cpu"
        
        self.thread_pool_size = thread_pool_size
        self.__executor = None
        self._params.update({
            "device": self.device,
            "batch_size": batch_size,
            "thread_pool_size": thread_pool_size
        })
        self.model_path = model_path
        self.params={
            "model": self.model_path,
            "normalize_embeddings": True
        }
    def __get_executor(self):
        """获取或创建线程池"""
        if self.__executor is None:
            from concurrent.futures import ThreadPoolExecutor
            self.__executor = ThreadPoolExecutor(
                max_workers=self.thread_pool_size,
                thread_name_prefix="embed_worker"
            )
        return self.__executor

    def init_model(self):
        if self._initialized and self._model is not None:
            return
        if not os.path.exists(self.model_name):
            raise ImportError(
                f"模型路径不存在: {self.model_name}"
                f"（请确认已下载模型，或传入正确的 model_path）"
            )
        
        try:
            from emotion_classifier.models.encoder import ONNXEncoder
            self._model = ONNXEncoder(
                self.model_path, # type: ignore
                tokenizer_dir=f"{self.model_path}/tokenizer"
            )
            self._initialized = True
            logger.info(f"SentenceTransformer模型加载成功: {self.model_name} on {self.device}")
            
        except ImportError as e:
            raise NotImplementedError(
                "请安装 sentence-transformers: pip install sentence-transformers"
            ) from e
        except Exception as e:
            raise ValueError(f"模型加载失败: {e}") from e

    async def embed(self, texts: Union[str, List[str]]):
        """异步嵌入文本（使用线程池）"""
        if self._model is None:
            self.init_model()
        
        loop = asyncio.get_event_loop()
        executor = self.__get_executor()
        return await loop.run_in_executor(
            executor,
            self.__embed,
            texts
        )

    def __embed(self,texts:Union[str,list[str]]):
        """
        对文本进行嵌入
        Parameters:
            text: [输入的文本或文本列表]
        Returns:
            np.ndarray: 嵌入后的向量
            dtype: np.float32
        """
        if self._model is None:
            raise ValueError("model is not initialized")
        if not texts:
            raise ValueError("texts is empty")
        self._single_input = isinstance(texts, str)
        if isinstance(texts, str):
            texts = [texts]
        try:
            embeddings = self._model.encode(
                texts,
                normalize=self.normalize,
                batch_size=self.batch_size
            )  # type: ignore
            if getattr(self, "_single_input", False) and len(embeddings) == 1:
                return embeddings[0]
            return embeddings
        except Exception as exc:
            raise ValueError("model encode error") from exc
    
    async def close(self) -> None:
        executor = getattr(self, "_SentenceEmbeddingAdapter__executor", None)
        if executor is not None:
            loop = asyncio.get_running_loop()
            try:
                await loop.run_in_executor(None, lambda: executor.shutdown(wait=True))
            except Exception:
                pass
            self.__executor = None
        self._model = None
        self._initialized = False
    
    def get_params(self):
        return self.params

class OpenAIEmbeddingAdapter(AsyncEmbeddingAdapter):
    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        api_base: str = "https://api.openai.com/v1",
        organization: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        normalize: bool = True
    ):
        super().__init__(
            model=model,
            normalize=normalize,
            batch_size=16,  # OpenAI批处理限制
            max_retries=max_retries
        )
        self.api_key = api_key
        self.api_base = api_base
        self.organization = organization
        self.timeout = timeout
        
        self._params.update({
            "api_base": api_base,
            "timeout": timeout
        })

    
    async def init_model(self) -> None:
        """初始化OpenAI客户端（异步）"""
        if self._initialized and self._model is not None:
            return
        
        try:
            from openai import AsyncOpenAI
            self._model = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.api_base,
                organization=self.organization,
                timeout=self.timeout,
                max_retries=self.max_retries
            ).embeddings
            self._initialized = True
            logger.info(f"OpenAI客户端初始化成功: {self.model_name}")
            
        except Exception as e:
            raise ValueError(f"OpenAI客户端初始化失败: {e}")
        
    @decorators.async_retry(
        retry_count=3,
        delay=1.0,
        backoff_factor=2.0,
        exceptions=(EmbeddingError,),
        raise_last_exception=True
    )
    async def embed(self, texts: Union[str, List[str]]) -> EmbeddingResult:
        """嵌入文本（OpenAI API，异步）"""
        if self._model is None:
            await self.init_model()
        
        if not texts:
            raise ValueError("文本不能为空")
        
        # 转换为列表
        self._single_input = isinstance(texts, str)
        if isinstance(texts, str):
            texts = [texts]
        import httpx
        try:
            response = await self._model.create(
                model=self.model_name,
                input=texts,
                encoding_format="float"
            ) # type: ignore
            
            embeddings = []
            for data in response.data:
                embeddings.append(array(data.embedding, dtype=float32))
            
            if self.normalize:
                for emb in embeddings:
                    emb /= linalg.norm(emb)
            if getattr(self, "_single_input", False) and len(embeddings) == 1:
                return embeddings[0]

            return embeddings
            
        except httpx.HTTPStatusError as e:
            logger.error(f"OpenAI API错误: {e.response.status_code} - {e.response.text}")
            raise EmbeddingError(f"API请求失败: {e.response.status_code}") from e
        except Exception as e:
            logger.error(f"OpenAI嵌入失败: {e}")
            raise EmbeddingError(f"嵌入失败: {e}") from e

class OllamaEmbeddingAdapter(AsyncEmbeddingAdapter):    
    def __init__(
        self,
        model: str = "nomic-embed-text",
        api_url: str = "http://localhost:11434",
        timeout: float = 60.0,
        max_retries: int = 3,
        normalize: bool = True
    ):
        super().__init__(
            model=model,
            normalize=normalize,
            batch_size=1,  # Ollama通常不支持批量
            max_retries=max_retries
        )
        
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout
        
        self._params.update({
            "api_url": api_url,
            "timeout": timeout
        })
    
    async def init_model(self) -> None:
        if self._initialized and self._model is not None:
            return
        
        try:
            from ...utils import http
            self._model=http.create_httpx_async_client(
                max_connections=10,
                timeout=self.timeout
            )
            self._initialized = True
            logger.info(f"Ollama客户端初始化成功: {self.api_url}")
            
        except Exception as e:
            raise ValueError(f"HTTP客户端初始化失败: {e}")
    
    async def _check_model_available(self) -> bool:
        """检查模型是否可用"""
        if self._model is None:
            await self.init_model()
        
        try:
            response = await self._model.get(f"{self.api_url}/api/tags")
            if response.status_code == 200:
                models = response.json().get("models", [])
                return any(model["name"] == self.model_name for model in models)
            return False
        except Exception:
            return False

    @decorators.async_retry(
        retry_count=3,
        delay=1.0,
        backoff_factor=2.0,
        exceptions=(EmbeddingError,),
        raise_last_exception=True
    )
    async def embed(self, texts: Union[str, List[str]]) -> EmbeddingResult:
        """嵌入文本（Ollama API，异步）"""
        if self._model is None:
            await self.init_model()
        
        if not texts:
            raise ValueError("文本不能为空")
        
        # 转换为列表
        self._single_input = isinstance(texts, str)
        if isinstance(texts, str):
            texts = [texts]

        embeddings: List[ndarray] = []
        endpoint = f"{self.api_url}/api/embeddings"
        import httpx
        for text in texts:
            try:
                response = await self._model.post(
                    endpoint,
                    json={
                        "model": self.model_name,
                        "prompt": text
                    }
                )
                response.raise_for_status()
                
                data = response.json()
                if "embedding" not in data:
                    raise EmbeddingError("响应中缺少embedding字段")
                
                embedding = array(data["embedding"], dtype=float32)
                
                if self.normalize:
                    norm = linalg.norm(embedding)
                    if norm > 0:
                        embedding /= norm
                embeddings.append(embedding)
                
            except httpx.HTTPStatusError as e:
                logger.error(f"Ollama API错误: {e.response.status_code} - {e.response.text}")
                raise EmbeddingError(f"API请求失败: {e.response.status_code}") from e
            except Exception as e:
                logger.error(f"Ollama嵌入失败: {e}")
                raise EmbeddingError(f"嵌入失败: {e}") from e
        
        if getattr(self, "_single_input", False) and len(embeddings) == 1:
            return embeddings[0]
        return embeddings