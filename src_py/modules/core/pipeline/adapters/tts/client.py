#httpx异步客户端
import asyncio
from typing import AsyncGenerator, List
import httpx

class TextSplitter:
    """智能文本分割器，用于流式TTS"""
    
    def __init__(self, max_chars: int = 50):
        self.max_chars = max_chars
        self._buffer = ""
        self._sentence_endings = set('。！？.!?\n')
        self._punctuation = set('，,、；;：: ')
    
    def feed(self, text: str) -> List[str]:
        """输入文本，返回可发送的句子列表"""
        self._buffer += text
        sentences = []
        while len(self._buffer) >= self.max_chars:
            # 找最近的句子结尾
            cut_pos = -1
            for i in range(self.max_chars - 1, -1, -1):
                if self._buffer[i] in self._sentence_endings:
                    cut_pos = i + 1
                    break
            if cut_pos == -1:
                # 没有句子结尾，找标点符号
                for i in range(self.max_chars - 1, -1, -1):
                    if self._buffer[i] in self._punctuation:
                        cut_pos = i + 1
                        break
            if cut_pos == -1:
                cut_pos = self.max_chars
            sentences.append(self._buffer[:cut_pos])
            self._buffer = self._buffer[cut_pos:]
        
        return sentences
    
    def flush(self) -> str:
        remaining = self._buffer
        self._buffer = ""
        return remaining

class AsyncGenerateTTSClient:
    def __init__(
        self,
        max_connections: int = 20,
        max_keepalive_connections: int = 10,
        timeout: float = 60.0,
        verify_ssl: bool = True,
        max_chars: int = 30,
    ):
        """
        初始化TTS客户端
        
        :param max_connections: 最大连接数
        :param max_keepalive_connections: 最大保持连接数
        :param timeout: 默认超时时间（秒）
        :param verify_ssl: 是否验证SSL证书
        """
        limits = httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive_connections
        )
        self.client = httpx.AsyncClient(
            limits=limits,
            timeout=timeout,
            verify=verify_ssl
        )
        self._adapters = {}
        self.text_splitter = TextSplitter(max_chars=max_chars)
        
    async def close(self):
        await self.client.aclose()
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def stream(self, method: str, url: str, **kwargs) -> AsyncGenerator[bytes, None]:
        async with self.client.stream(method, url, **kwargs) as response:
            async for chunk in response.aiter_bytes():
                yield chunk
                await asyncio.sleep(0.01)