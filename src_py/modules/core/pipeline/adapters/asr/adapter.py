from abc import ABC, abstractmethod
import asyncio
import base64
from dataclasses import dataclass
from enum import Enum
import json
from types import CoroutineType
from typing import Any, AsyncGenerator, Optional
import uuid
import httpx
import numpy as np
from modules.utils.util import get_device

@dataclass
class ASRConfig:
    """ASR 配置"""
    model_type: str = "whisper"  # whisper / sensevoice / paraformer
    model_variant: str = "small"
    language: str = "zh"
    sample_rate: int = 16000
    chunk_size: int = 5120  # 160ms @ 16kHz
    vad_enabled: bool = True
    vad_threshold: float = 0.5
    beam_size: int = 5
    temperature: float = 0.0
    
    # 流式参数
    streaming_mode: bool = True
    partial_results: bool = True
    min_words_per_chunk: int = 2
    max_wait_time: float = 2.0  # 最大等待时间

class _ASRBaseAdapter(ABC):
    def __init__(self):
        self.model = None
        self.model = None
        self.processor = None
        self._audio_buffer = np.array([], dtype=np.float32)
        self._text_buffer = ""
        self._last_result_time = 0.0
        self.config = ASRConfig()
        self.initialized = False
    
    def initialize(self,**kwargs) -> CoroutineType:
        raise NotImplementedError

    @abstractmethod
    def transcribe(self, audio_bytes: bytes) -> CoroutineType:
        raise NotImplementedError
    
    @abstractmethod
    def transcribe_stream(self, audio_bytes: bytes, is_final: bool=False) -> AsyncGenerator[str, None]:
        raise NotImplementedError
    
    def close(self) -> None:
        self.model = None
        self.processor = None
        self.initialized = False

# class BaiduASRAdapter(_ASRBaseAdapter):
#     """
#         使用百度实时语音识别 API（WebSocket），实现边录边识别

#         Reference：
#             <a href="https://ai.baidu.com/ai-doc/SPEECH/Vk38lxily">百度实时语音识别 API 文档</a>
#     """
#     WS_URL = "wss://vop.baidu.com/realtime_asr"
    
#     def __init__(
#         self,
#         api_key: str,
#         secret_key: str,
#         dev_pid: int = 15372,  # 普通话(支持简单的英文识别) 15373: 英语
#         sample_rate: int = 16000,
#         enable_vad: bool = True,  # 启用VAD（语音活动检测）
#         max_silence_ms: int = 1500,  # 最大静音时长（毫秒）
#     ):
#         self.api_key = api_key
#         self.secret_key = secret_key
#         self.dev_pid = dev_pid
#         self.sample_rate = sample_rate
#         self.enable_vad = enable_vad
#         self.max_silence_ms = max_silence_ms
        
#         self.__access_token: Optional[str] = None
#         self.__cuid = str(uuid.uuid4()).replace('-', '')[:20]
#         self.client = httpx.AsyncClient(timeout=30)
#         self._ws_client: Optional[Any] = None  # WebSocket连接
        
#     async def initialize(self) -> None:
#         """初始化：获取 access_token"""
#         if not self.initialized:
#             self.__access_token = await self._get_access_token()
#             self.initialized = True
        
    
#     async def _get_access_token(self) -> str:
#         """
#         使用 AK，SK 生成鉴权签名（Access Token）
#         Returns
#           str: access_token
#         """
#         url = "https://aip.baidubce.com/oauth/2.0/token"
#         params = {
#             "grant_type": "client_credentials",
#             "client_id": self.api_key,
#             "client_secret": self.secret_key
#         }
#         response = await self.client.post(url, params=params)
#         response.raise_for_status()
#         response_data = response.json()
#         access_token = str(response_data.get("access_token"))
#         if not access_token:
#             raise RuntimeError(f"获取百度 access_token 失败: {response_data}")
#         return access_token
    
#     async def transcribe(self, audio_bytes: bytes) -> str:
#         """
#         非流式转录完整音频
        
#         使用百度 REST API 进行整段识别
#         """
#         if not self._initialized:
#             await self.initialize()
            
#         url = "https://vop.baidu.com/server_api"
        
#         # 确保音频格式正确（16kHz, 16bit, 单声道 WAV）
#         audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
#         data_len = len(audio_bytes)
        
#         payload = {
#             "format": "wav",
#             "rate": self.sample_rate,
#             "channel": 1,
#             "cuid": self.__cuid,
#             "speech": audio_base64,
#             "len": data_len,
#             "token": self.__access_token,
#             "dev_pid": self.dev_pid,
#         }
#         headers = {
#             'Content-Type': 'application/json',
#             'Accept': 'application/json'
#         }
        
#         response = await self.client.post(url, json=payload, headers=headers)
#         response.raise_for_status()
#         response_data = response.json()
        
#         if response_data.get('err_no') != 0:
#             raise RuntimeError(f"百度ASR识别失败: {response_data}")
        
#         return response_data['result'][0]
    
#     async def transcribe_stream(self,audio_bytes: bytes) -> AsyncGenerator[str, None]:
#         """
#         流式识别
        
#         使用百度实时语音识别 WebSocket API
#         真正的流式识别
        
#         使用百度实时语音识别 WebSocket API
#         每次收到完整的句子就 yield 返回
#         """
#         if not self._initialized:
#             await self.initialize()
        
#         # 创建 WebSocket 连接
#         ws_url = f"{self.WS_URL}?access_token={self.__access_token}&dev_pid={self.dev_pid}&cuid={self.__cuid}"
#         from websockets import connect
#         async with connect(ws_url, ping_interval=None) as websocket:
#             # 发送开始帧
#             start_frame = self.__create_start_frame()
#             await websocket.send(json.dumps(start_frame))
            
#             # 接收开始确认
#             start_response = await websocket.recv()
#             start_data = json.loads(start_response)
#             if start_data.get('err_no') != 0:
#                 raise RuntimeError(f"百度流式ASR启动失败: {start_data}")
            
#             # 发送音频数据并接收识别结果
#             buffer = b""
#             sequence_id = 1
            
#             is_first_chunk = True
#             # async for audio_chunk in  audio_gernerator:
#                 # 每 160ms 的音频数据发送一次（约 2560 字节）
#                 # 百度推荐每帧 160ms 音频
#                 # buffer+=audio_chunk
#         frame_size = int(self.sample_rate * 0.16 * 2)  # 16bit = 2 bytes
        
#         while len(buffer) >= frame_size:
#             frame_data = buffer[:frame_size]
#             buffer = buffer[frame_size:]
            
#             # 发送音频帧
#             mid_frame = self.__create_mid_frame(frame_data, sequence_id)
#             await websocket.send(json.dumps(mid_frame))
#             sequence_id += 1
            
#             # 接收可能的识别结果
#             try:
#                 response = await asyncio.wait_for(
#                     websocket.recv(), 
#                     timeout=0.01  # 短超时，不阻塞音频发送
#                 )
#                 response_data = json.loads(response)
                
#                 # 处理识别结果
#                 result = self.__parse_stream_response(response_data)
#                 if result:
#                     yield result        
#             except asyncio.TimeoutError:
#                 # 没有结果，继续发送音频
#                 pass
#             except Exception as e:
#                 print(f"接收识别结果异常: {e}")
            
#             # 发送剩余的音频数据
#             if buffer:
#                 mid_frame = self.__create_mid_frame(buffer, sequence_id)
#                 await websocket.send(json.dumps(mid_frame))
#                 sequence_id += 1
#                 await asyncio.sleep(0.1)
            
#             # 发送结束帧
#             end_frame = self.__create_end_frame(sequence_id)
#             await websocket.send(json.dumps(end_frame))
            
#             # 收集最终的识别结果
#             final_results = []
#             try:
#                 while True:
#                     response = await asyncio.wait_for(
#                         websocket.recv(),
#                         timeout=2.0
#                     )
#                     response_data = json.loads(response)
                    
#                     result = self.__parse_stream_response(response_data, is_final=True)
#                     if result:
#                         final_results.append(result)
                        
#                     # 检查是否结束
#                     if response_data.get('type') == 'FIN' or response_data.get('err_no') == 0:
#                         break
                        
#             except asyncio.TimeoutError:
#                 pass
            
#             # 合并最终结果
#             if final_results:
#                 yield "".join(final_results)
    
#     def __create_start_frame(self,appid: str="",appkey: str="") -> dict:
#         return {
#             "type": "START",
#             "data": {
#                 "appid": appid,
#                 "appkey": appkey,
#                 "dev_pid": self.dev_pid,
#                 "cuid": self.__cuid,
#                 "format": "pcm",
#                 "sample": self.sample_rate,
#                 "enable_vad": self.enable_vad,
#                 "max_silence_ms": self.max_silence_ms,
#             }
#         }
    
#     def __create_mid_frame(self, audio_data: bytes, sequence_id: int) -> dict:
#         """创建中间帧"""
#         audio_base64 = base64.b64encode(audio_data).decode('utf-8')
#         return {
#             "type": "MID_DATA",
#             "data": {
#                 "seq": sequence_id,
#                 "audio": audio_base64,
#             }
#         }
    
#     def __create_end_frame(self, sequence_id: int) -> dict:
#         """创建结束帧"""
#         return {
#             "type": "FINISH",
#             "data": {
#                 "seq": sequence_id,
#             }
#         }
    
#     def __parse_stream_response(self, response_data: dict, is_final: bool = False) -> Optional[str]:
#         """    
#         百度流式响应格式：
#         ```json
#         {
#             "err_no": 0,
#             "err_msg": "success.",
#             "type": "MID_DATA" | "FIN_DATA" | "ERROR",
#             "result": {
#                 "text": "识别文本",
#                 "words": [...]
#             }
#         }
#         ```
#         """
#         err_no = response_data.get('err_no', -1)
#         if err_no != 0:
#             return None
        
#         response_type = response_data.get('type', '')
        
#         # 只处理中间结果和最终结果
#         if response_type in ('MID_DATA', 'FIN_DATA'):
#             result = response_data.get('result', {})
#             text = result.get('text', '')
#             if text:
#                 return text
        
#         return None
    
#     async def close(self) -> None:
#         """关闭连接"""
#         if self._ws_client:
#             await self._ws_client.close()
#         await self.client.aclose()
#         super().close()
#         self._initialized = False

# class TencentCloudASRAdapter(_ASRBaseAdapter):
#     """腾讯云实时语音识别适配器"""
    
#     def __init__(self, app_id: str, secret_id: str, secret_key: str):
#         self.app_id = app_id
#         self.secret_id = secret_id
#         self.secret_key = secret_key
#         self.client = None
#         self._session_id = None
        
#     async def initialize(self) -> None:
#         """初始化腾讯云ASR客户端"""
#         try:
#             from tencentcloud.common import credential # type: ignore
#             from tencentcloud.asr.v20190614 import asr_client, models # type: ignore
#             cred = credential.Credential(self.secret_id, self.secret_key)
#             self.client = asr_client.AsrClient(cred, "ap-guangzhou")
#             self._session_id = f"session_{id(self)}"
#         except ImportError:
#             raise ImportError("请安装 tencentcloud-sdk-python")
    
#     async def transcribe(self, audio_data: bytes) -> str:
#         """非流式转录"""
#         if not self.client:
#             await self.initialize()
        
#         # 将音频转为base64
#         audio_base64 = base64.b64encode(audio_data).decode('utf-8')
        
#         try:
#             from tencentcloud.asr.v20190614 import models # type: ignore
#             req = models.SentenceRecognitionRequest()
#             req.ProjectId = 0
#             req.SubServiceType = 2
#             req.EngSerViceType = "16k_zh"
#             req.SourceType = 1
#             req.VoiceFormat = "wav"
#             req.UssrVoiceKeyStr = "test"
#             req.Data = audio_base64
#             req.DataLen = len(audio_data)
            
#             resp = self.client.SentenceRecognition(req) # type: ignore
#             return resp.Result
#         except Exception as e:
#             raise RuntimeError(f"ASR转录失败: {e}")
    
#     async def transcribe_stream(self, audio_chunk: bytes)  -> AsyncGenerator[str, None]:
#         """流式转录 - 使用腾讯云Flash ASR"""
#         if not self.client:
#             await self.initialize()
        
#         try:
#             from tencentcloud.asr.v20190614 import models # type: ignore
            
#             # 模拟流式处理，实际应使用WebSocket实时ASR
#             if len(audio_chunk) >= 32000:  # 约2秒音频
#                 result = await self.transcribe(audio_chunk)
#                 yield result
#                 buffer = b""
            
#             # 处理剩余音频
#             if buffer:
#                 result = await self.transcribe(buffer)
#                 yield result
                
#         except Exception as e:
#             raise RuntimeError(f"流式ASR失败: {e}")
    
#     async def close(self) -> None:
#         self.client = None

class WhisperASRAdapter(_ASRBaseAdapter):
    def __init__(
            self, 
            model_size: str = "base",
            language: str = "zh"
        ):
        self.model_size = model_size
        self.device = get_device()
        self.language = language
        
    
    async def __transcribe_whisper(self, is_final: bool=False) -> AsyncGenerator[str, None]:
        audio = self._audio_buffer.copy()
        
        # 如果音频太短，填充静音
        if len(audio) < self.config.sample_rate:
            audio = np.pad(audio, (0, self.config.sample_rate - len(audio)))
        
        # 转写
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self.model.transcribe(
                audio,
                language=self.config.language,
                beam_size=self.config.beam_size,
                temperature=self.config.temperature,
                condition_on_previous_text=True
            )
        )
        
        # 提取文本
        segments = result.get("segments", []) # type: ignore
        new_text = ""
        
        for seg in segments:
            text = seg.get("text", "").strip()
            if text and text not in self._text_buffer:
                new_text += text
        
        if new_text:
            self._text_buffer += new_text
            yield new_text
        
        # 如果不是最终结果，保留部分音频用于下次
        if not is_final:
            keep_samples = int(self.config.sample_rate * 0.5)  # 保留0.5秒
            if len(self._audio_buffer) > keep_samples:
                self._audio_buffer = self._audio_buffer[-keep_samples:]

    async def initialize(self,model_path: str="") -> None:
        try:
            from faster_whisper import WhisperModel
            self.model = WhisperModel(
                model_path or self.model_size, 
                device=self.device,
                language=self.language
            )
            self.initialized = True
        except ImportError:
            raise ImportError("请安装 faster-whisper")

    async def transcribe(self, audio_bytes: bytes) -> str:
        if not self.model:
            await self.initialize()
        from numpy import frombuffer,float32,int16
        # 将WAV字节转为numpy数组
        audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        self._audio_buffer = np.concatenate([self._audio_buffer, audio_array])
        segments, info = self.model.transcribe(audio_array, beam_size=self.config.beam_size) # type: ignore
        return "".join(segment.text for segment in segments)
    
    async def transcribe_stream(
            self,
            audio_bytes: bytes,
            is_final: bool = False
        ) -> AsyncGenerator[str, None]:
        if not self.model:
            await self.initialize()
        
        audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        self._audio_buffer = np.concatenate([self._audio_buffer, audio_array])
        # 检查是否需要处理
        if len(self._audio_buffer) < self.config.sample_rate * 0.5 and not is_final:
            return  # 不足0.5秒不处理
        try:
            async for text in self.__transcribe_whisper(is_final):
                yield text
        except Exception as e:
            raise RuntimeError(f"Whisper转录失败: {e}")
        
        