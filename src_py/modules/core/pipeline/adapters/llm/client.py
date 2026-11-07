from abc import ABC, abstractmethod
import json
from typing import AsyncGenerator, Dict, Generic, Literal, Optional, TypeVar, Union
import httpx

T = TypeVar("T", bound=dict)

DEFAULT_RETRY_DELAY = 1.0
MAX_CONNECTIONS = 100
MAX_KEEPALIVE_CONNECTIONS = 20

class _BaseLLMClient(ABC):
    """LLM客户端基类"""
    
    def __init__(
        self, 
        provider: str, 
        api_url: str, 
        api_key: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 3
    ):
        self.provider = provider
        self.api_url = api_url
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.__client= None
        self.__headers = {"Content-Type": "application/json"}
        if api_key:
            self.__headers["Authorization"] = f"Bearer {api_key}"
    
    async def __aenter__(self):
        await self.__ensure_client()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def __ensure_client(self) -> httpx.AsyncClient:
        """确保HTTP客户端已初始化"""
        if self.__client is None or self.__client.is_closed:
            self.__client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout, connect=10.0),
                limits=httpx.Limits(
                    max_connections=MAX_CONNECTIONS,
                    max_keepalive_connections=MAX_KEEPALIVE_CONNECTIONS
                ),
                headers=self.__headers,
                follow_redirects=True
            )
        return self.__client
    
    @abstractmethod
    async def stream_request(self, data: Dict, headers: Optional[Dict] = None) -> AsyncGenerator[str, None]:
        """流式请求"""
        pass
    
    @abstractmethod
    async def request(self, data: Dict, headers: Optional[Dict] = None) -> Dict:
        """普通请求"""
        pass
    
    async def close(self):
        """关闭客户端连接"""
        if self.__client and not self.__client.is_closed:
            await self.__client.aclose()
        self.__client = None

class OpenAIClient(_BaseLLMClient):
    """OpenAI兼容客户端（使用httpx）"""
    
    def __init__(
        self, 
        api_url: str, 
        api_key: str, 
        timeout: float = 60.0,
        max_retries: int = 3
    ):
        super().__init__("openai", api_url, api_key, timeout, max_retries)
        
    async def stream_request(self, data: Dict, headers: Optional[Dict] = None) -> AsyncGenerator[str, None]:
        """OpenAI流式请求"""
        try:
            client = await self.__ensure_client()
            
            # 使用AsyncOpenAI的流式接口
            stream = await client.chat.completions.create(**data)
            
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content
                        
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP错误: {e.response.status_code} - {e.response.text}"
            raise Exception(error_msg) from e
        except httpx.TimeoutException as e:
            raise Exception("请求超时") from e
        except Exception as e:
            raise

    async def request(self, data: Dict, headers: Optional[Dict] = None) -> Dict:
        try:
            client = await self.__ensure_client()
            
            response = await client.chat.completions.create(**data)
            return response.choices[0].message.model_dump()
            
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP错误: {e.response.status_code} - {e.response.text}"
            raise Exception(error_msg) from e
        except httpx.TimeoutException as e:
            raise Exception("请求超时") from e
        except Exception as e:
            raise
    
    #重写__ensure_client方法用于适配AsyncOpenAI客户端
    async def __ensure_client(self):
        if self.__client is None:
            if not self.api_key:
                raise ValueError(f"{self.provider}需要api_key参数")
            if not self.api_url:
                raise ValueError(f"{self.provider}需要api_url参数")
            from openai import AsyncOpenAI
            self.__client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.api_url,
                timeout=httpx.Timeout(self.timeout),
                max_retries=self.max_retries
            )
        return self.__client
    
    async def close(self):
        if self.__client and not self.__client.is_closed:
            await self.__client.close()
        self.__client = None

class AsyncGenerateLLMClient(_BaseLLMClient,Generic[T]):
    PrvoidType=Literal["chatgpt","ollama","deepseek"]

    def __init__(
        self, 
        provider: Union[str,PrvoidType], 
        api_url: Optional[str] = None, 
        api_key: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 3
    ):
        if not api_url:
            api_url=self.__get_default_api_url(provider)
        super().__init__(provider, api_url, api_key, timeout, max_retries)
        self.__chunk_parser = self.__get_chunk_parser(provider)
        if api_key:
            self.__headers["Authorization"] = f"Bearer {api_key}" # 供应商类型

    def __get_chunk_parser(self, provider: str):
        """获取流式响应解析器"""
        parsers = {
            "ollama": self.__parse_ollama_chunk,
            "deepseek": self.__parse_openai_chunk,
            "chatgpt": self.__parse_openai_chunk
        }
        if provider in parsers:
            return parsers[provider]
        else:
            return self.__parse_generic_chunk
    
    def __parse_openai_chunk(self, chunk_data: Dict) -> Optional[str]:
        """解析OpenAI格式的流式响应"""
        if "choices" in chunk_data and chunk_data["choices"]:
            delta = chunk_data["choices"][0].get("delta", {})
            return delta.get("content")
        return None
    
    def __parse_ollama_chunk(self, chunk_data: Dict) -> Optional[str]:
        """解析Ollama格式的流式响应"""
        message = chunk_data.get("message", {})
        return message.get("content")
    
    def __parse_generic_chunk(self, chunk_data: Dict) -> Optional[str]:
        """解析通用格式的流式响应"""
        # 尝试多种可能的字段
        for field in ["content", "text", "message", "delta"]:
            if field in chunk_data:
                value = chunk_data[field]
                if isinstance(value, str):
                    return value
                elif isinstance(value, dict):
                    return value.get("content") or value.get("text")
        return None

    def __get_default_api_url(self,prvoid:str):
        urls={
            "chatgpt":"https://api.openai.com/v1",
            "deepseek":"https://api.deepseek.com",
            "ollama":"http://localhost:11434/"
        }
        if prvoid in urls:
            return urls[prvoid]
        else:
            raise ValueError("不支持的供应商")

    async def stream_request(
        self,
        data:T,
        headers:Optional[dict]=None,
        timeout:float=60.0
    ):
        client = await self.__ensure_client()
        request_headers = self.__headers.copy()
        if headers:
            request_headers.update(headers)
        try:
            async with client.stream(
                "POST",
                self.api_url,
                json=data,
                headers=request_headers
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    # 处理SSE格式
                    if line.startswith("data: "):
                        line = line[6:].strip()
                    if line == "[DONE]":
                        break
                    try:
                        chunk_data = json.loads(line)
                        content = self.__chunk_parser(chunk_data)
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP错误: {e.response.status_code}"
            try:
                error_text = e.response.text
                error_msg += f" - {error_text}"
            except:
                pass
            raise Exception(error_msg) from e
        except httpx.TimeoutException as e:
            raise Exception("请求超时") from e
        except Exception as e:
            raise
    
    async def request(self, data: Dict, headers: Optional[Dict] = None) -> Dict:
        """HTTP普通请求"""
        client = await self.__ensure_client()
        
        request_headers = self.__headers.copy()
        if headers:
            request_headers.update(headers)
        
        try:
            response = await client.post(
                self.api_url,
                json=data,
                headers=request_headers
            )
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP错误: {e.response.status_code}"
            error_text = e.response.text
            error_msg += f" - {error_text}"
            raise Exception(error_msg) from e
        except httpx.TimeoutException as e:
            raise Exception("请求超时") from e
        except Exception as e:
            raise