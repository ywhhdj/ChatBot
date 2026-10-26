from abc import ABC, abstractmethod
from enum import Enum
from types import CoroutineType
from typing import Optional, List, Dict, Any, AsyncGenerator

from regex import T
from . import client, models

DEFAULT_RETRY_DELAY = 1.0
MAX_CONNECTIONS = 100
MAX_KEEPALIVE_CONNECTIONS = 20

class _LLMBaseAdapter(ABC):
    #是否为本地0,API1
    name: str
    description: str
    local: int= 0
    tags: Optional[List[str]] = None

    def __init__(self,model: str = ""):
        super().__init__()
        self.model: str = model
        self.params: Optional[models.SamplingParams] = None
        self._client= None
        self.last_tool_calls: List[Dict[str, Any]] = []
        self._tool_call_cache: Dict[int, Dict[str, Any]] = {}

    @abstractmethod
    def initialize_client(self) -> 'client._BaseLLMClient':
        pass

    from ...models import AITool
    @abstractmethod
    def generate_text_stream(
        self, 
        messages: List[Dict], 
        tools: Optional[AITool] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024
    ) -> AsyncGenerator[str, None]:
        raise NotImplementedError

    @abstractmethod
    def generate_text(
        self, message: list,
        tools: Optional[AITool] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024
    ) -> CoroutineType:
        raise NotImplementedError

    def _build_request_data(
            self, 
            messages: List[Dict], 
            tools: Optional[List] = None, 
            stream: bool = False,
            temperature: float = 0.7,
            max_tokens: int = 1024
        ) -> Dict:
        """构建请求数据"""
        data = {
            **self.params.model_dump(), # type:ignore
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        if tools:
            data["tools"] = tools
            data["tool_choice"] = "auto"
        return data
    
    def get_params(self) -> Dict[str, Any]:
        return self.params.model_dump() # type:ignore
    
    def close(self):
        import asyncio
        if self._client is not None:
            if asyncio.iscoroutinefunction(self._client.close):
                asyncio.run(self._client.close())

class ChatGPTLLMAdapter(_LLMBaseAdapter):
    tags: Optional[List[str]] = ["chatgpt"]
    
    def __init__(
        self, 
        api_url: str, 
        api_key: str, 
        model: str = "gpt-3.5-turbo",
        timeout: float=20,
        max_retries: int = 1
    ):
        super().__init__()
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.params = models.ChatGPTParams(
            temperature=0.7,
            max_tokens=1024,
            top_p=0.9,
            frequency_penalty=0.0,
            presence_penalty=0.0
        )
    
    async def initialize_client(self) -> client.OpenAIClient:
        if self._client is None:
            self._client = client.OpenAIClient(
                api_url=self.api_url,
                api_key=self.api_key,
                timeout=self.timeout,
                max_retries=self.max_retries
            )
        return self._client
    
    async def generate_text_stream(
            self, 
            messages: List[Dict], 
            tools: Optional[List] = None,
            temperature: float = 0.7,
            max_tokens: int = 1024
        ) -> AsyncGenerator[str, None]:
        """生成流式文本"""
        client = await self.initialize_client()
        data = self._build_request_data(
            messages, tools, 
            stream=True,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        try:
            async for chunk in client.stream_request(data):
                yield chunk
                
            # 保存工具调用
            if self._tool_call_cache:
                self.last_tool_calls = list(self._tool_call_cache.values())
                self._tool_call_cache.clear()
                
        except Exception as e:
            raise
    
    async def generate_text(
        self, 
        messages: List[Dict], 
        tools: Optional[List] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024
    ) -> str:
        client = await self.initialize_client()
        data = self._build_request_data(
            messages, 
            tools, 
            stream=False,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        try:
            response = await client.request(data)
            message = response
            
            # 提取工具调用
            if message.get("tool_calls"):
                self.last_tool_calls = message["tool_calls"]
            
            return message.get("content", "")
            
        except Exception as e:
            raise

class OllamaLLMAdapter(_LLMBaseAdapter):
    local: int = 1
    tags: Optional[List[str]] = ["ollama"]
    
    def __init__(
        self, 
        model: str, 
        api_url: str = "http://localhost:11434/api/chat",
        timeout: float = 20.0,
        max_retries: int = 3
    ):
        super().__init__(model)
        self.api_url = api_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.model = model
        self.params = models.OllamaParams()
    
    async def initialize_client(self):
        if self._client is None:
            self._client = client.AsyncGenerateLLMClient(
                provider="ollama",
                api_url=self.api_url,
                timeout=self.timeout,
                max_retries=self.max_retries
            )
        return self._client
    
    async def generate_text_stream(
            self, 
            messages: List[Dict], 
            tools: Optional[List] = None,
            temperature: float = 0.7,
            max_tokens: int = 1024
        ) -> AsyncGenerator[str, None]:
        """生成流式文本"""
        client = await self.initialize_client()
        
        data = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **self.params.model_dump() # type:ignore
        }
        
        if tools:
            data["tools"] = tools
        
        try:
            async for chunk in client.stream_request(data):
                yield chunk
                
        except Exception as e:
            raise
    
    async def generate_text(
            self, 
            messages: List[Dict], 
            tools: Optional[List] = None,
            temperature: float = 0.7,
            max_tokens: int = 1024
        ) -> str:
        client = await self.initialize_client()
        data = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **self.params.model_dump() # type:ignore
        }
        
        if tools:
            data["tools"] = tools
        
        try:
            response = await client.request(data)
            return response.get("message", {}).get("content", "")
            
        except Exception as e:
            raise

class DeepseekLLMAdapter(_LLMBaseAdapter):

    def __init__(
        self, 
        api_key: str, 
        model: str = "deepseek-v4-flash",
        timeout: float = 60.0,
        max_retries: int = 3
    ):
        super().__init__()
        self.api_key = api_key
        self.model = model
        if model not in ["deepseek-v4-flash", "deepseek-v4-pro"]:
            raise ValueError(f"Invalid model: {model}")
        self.timeout = timeout
        self.max_retries = max_retries
        self.params = models.DeepSeekParams(
            temperature=0.7,
            max_tokens=1024,
            top_p=0.9,
            frequency_penalty=0.0,
            presence_penalty=0.0
        )
    
    async def initialize_client(self):
        if self._client is None:
            self._client = client.AsyncGenerateLLMClient(
                provider="deepseek",
                api_key=self.api_key,
                timeout=self.timeout,
                max_retries=self.max_retries
            )
        return self._client
    
    async def generate_text_stream(
        self, 
        messages: List[Dict], 
        tools: Optional[List] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024
    ) -> AsyncGenerator[str, None]:
        client = await self.initialize_client()
        data = self._build_request_data(
            messages, 
            tools, 
            stream=True,
            temperature=temperature,
            max_tokens=max_tokens
        )
        try:
            async for chunk in client.stream_request(data):
                yield chunk
        except Exception as e:
            raise
    
    async def generate_text(
        self, 
        messages: List[Dict], 
        tools: Optional[List] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024
    ) -> str:
        client = await self.initialize_client()
        data = self._build_request_data(
            messages, 
            tools, 
            stream=False,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        try:
            response = await client.request(data)
            message = response
            return message.get("content", "")
            
        except Exception as e:
            raise
