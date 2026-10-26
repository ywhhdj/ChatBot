from abc import ABC, abstractmethod
import asyncio
import os
from types import CoroutineType
from typing import AsyncGenerator,Optional, Union

from .client import AsyncGenerateTTSClient
from . import models

class _TTSBaseAdapter(ABC):
    def __init__(self) -> None:
        self.params= None
        self.client: Optional[AsyncGenerateTTSClient] = None

    def initialize_client(self):
        self.client=AsyncGenerateTTSClient()

    @abstractmethod
    def generate_voice_stream(self, text: str,**kwagrs) -> AsyncGenerator[bytes, None]:
        raise NotImplementedError("generate_voice_stream method must be implemented")

    @abstractmethod
    def generate_voice(self, text: str,**kwagrs) -> CoroutineType:
        """生成语音"""
        raise NotImplementedError("generate_voice method must be implemented")

    def get_audio_format(self) -> str:
        return "wav"

    def get_audio_sample_rate(self) -> int:
        return 44100

    def get_audio_channels(self) -> int:
        return 1

    def get_audio_sample_width(self) -> int:
        return 2
    
    def get_params(self) -> dict:
        return self.params.__dict__
    
    async def close(self):
        if self.client is not None:
            await self.client.close()
    
    def update_params(self,text:str,**kwargs):
        if self.params is None:
            self.params= dict()
        self.params["text"]=text
        self.params.update(kwargs)

# class EdgeTTSAdapter(_TTSBaseAdapter):
#     def __init__(self) -> None:
#         super().__init__()
#         self.params= dict(
#             model_uuid="",
#             speaker_uuid="",
#             style_id=0,
#             style_name="",
#             language="ja",
#             use_ssml=True,
#             speaking_rate=1.0,
#             emotional_intensity=1.0,
#             tempo_dynamics=1.0,
#             pitch=0.0,
#             volume=1.0,
#             leading_silence_seconds=0.1,
#             trailing_silence_seconds=0.1,
#             line_break_silence_seconds=0.4,
#             output_format="wav",
#             output_sampling_rate=44100,
#             output_audio_channels="mono",
#             text=""
#         )
    
#     def initialize_client(self):
#         try:
#             import edge_tts
#         except Exception as e:
#             raise ValueError(f"EdgeTTSAdapter initialize_client failed: {e}")

#     def generate_voice(self, text: str) -> CoroutineType[Any, Any, bytes]:
        
class AIVISAdapter(_TTSBaseAdapter):
    def __init__(
            self,
            api_url: str,
            api_key: str,
            model_uuid: str,
            speaker_uuid: Optional[str] = None,
            style_id: Optional[int] = None,
            style_name: Optional[str] = None,
            audio_format: str = "mp3", 
            language: str = "ja"
        ):
        """
        初始化AIVIS适配器
        
        :param api_url: AIVIS API地址
        :param model_uuid: 语音合成模型的UUID (必须)
        :param speaker_uuid: 语音合成模型的说话人UUID (可选)
        :param style_id: 风格ID (0-31, 与style_name互斥)
        :param style_name: 风格名称 (与style_id互斥)
        :param audio_format: 音频格式 (wav/flac/mp3/aac/opus)
        :param lan: 语言 (BCP47格式, 默认"ja"，目前仅支持ja)
        """
        super().__init__()
        # 处理URL末尾斜杠，避免重复
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.params= dict(
            model_uuid=model_uuid,
            speaker_uuid=speaker_uuid,
            style_id=style_id,
            style_name=style_name,
            language=language,
            use_ssml=True,
            speaking_rate=1.0,
            emotional_intensity=1.0,
            tempo_dynamics=1.0,
            pitch=0.0,
            volume=1.0,
            leading_silence_seconds=0.1,
            trailing_silence_seconds=0.1,
            line_break_silence_seconds=0.4,
            output_format=audio_format,
            output_sampling_rate=44100,
            output_audio_channels="mono",
            text=""
        )

        # 移除值为None的参数
        self.params = {k: v for k, v in self.params.items() if v is not None}
        
        # 验证style_id和style_name是否同时指定
        if style_id is not None and style_name is not None:
            raise ValueError("style_id和style_name不能同时指定，只能选择其一")

    def __generate_headers(self, text: str):
        """
        生成前调用函数，设置text参数
        
        :param text: 要转换为语音的文本
        """
        # 设置正确的Accept头
        output_format = self.params.get("output_format", "mp3")
        content_types = {
            "wav": "audio/wav",
            "flac": "audio/flac",
            "mp3": "audio/mpeg",
            "aac": "audio/aac",
            "opus": "audio/ogg; codecs=opus"
        }
        accept_header = content_types.get(str(output_format), "audio/mpeg")
        # 构建请求头
        return {
            "Accept": accept_header,
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

    async def generate_voice_stream(self, text: str,**kwargs) -> AsyncGenerator[bytes, None]:
        if self.client is None:
            raise RuntimeError("ATS客户端未初始化")
        headers = self.__generate_headers(text)
        self.update_params(text,**kwargs)
        try:
            sentences = self.client.text_splitter.feed(text)
            for sentence in sentences:
                self.params["text"] = sentence
                async for chunk in self.client.stream(
                    "GET",
                    self.api_url,
                    json=self.params,
                    headers=headers
                ):
                    yield chunk
                    await asyncio.sleep(0.01)
            remaining = self.client.text_splitter.flush()
            if remaining.strip():
                self.params["text"]=remaining
                async for chunk in self.client.stream(
                    "GET",
                    self.api_url,
                    params=self.params,
                    headers=headers
                ):
                    yield chunk
                    await asyncio.sleep(0.01)
            self.params["text"] = text
        except Exception as e:
            raise RuntimeError(f"AIVIS TTS请求失败: {e}")
    
    async def generate_voice(self, text: str):
        if self.client is None:
            self.initialize_client()
        try:
            chunks = []
            async for chunk in self.generate_voice_stream(text):
                chunks.append(chunk)
            return b''.join(chunks)
        except Exception as e:
            raise RuntimeError(f"AIVIS TTS请求失败: {e}")
    
    async def close(self) -> None:
        if self.client:
            await self.client.close()

    def get_params(self):
        """
        获取当前适配器的参数
        :return: 参数字典
        """
        return {k: v for k, v in self.params.items()
                if isinstance(v, (str, int, float, bool))}

class BV2Adapter(_TTSBaseAdapter):
    def __init__(self, api_url: str):
        super().__init__()
        self.api_url = api_url
        self.params= models.BV2Params(
            speaker_id=0,
            audio_format="wav",
            lang="zh",
            length=1.0,
            noise=0.33, # 采样噪声比例
            noisew=0.4, # SDP噪声
            segment_size=50, # 分段阈值
            sdp_radio=0.2, # SDP/DP混合比
            text="", # 文本
        )

    async def generate_voice_stream(self, text:str,**kwargs) -> AsyncGenerator[models.TTSResult, None]:
        if self.client is None:
            raise RuntimeError("BV2客户端未初始化")
        self.update_params(text,**kwargs)
        try:
            sentences = self.client.text_splitter.feed(text)
            for sentence in sentences:
                self.params["text"] = sentence
                async for chunk in self.client.stream(
                    "POST",
                    self.api_url,
                    params=self.params.__dict__
                ):
                    yield models.TTSResult(audio=chunk)
                    await asyncio.sleep(0.01)
            remaining = self.client.text_splitter.flush()
            if remaining.strip():
                self.params["text"]=remaining
                async for chunk in self.client.stream(
                    "POST",
                    self.api_url,
                    params=self.params.__dict__
                ):
                    yield models.TTSResult(audio=chunk)
                    await asyncio.sleep(0.01)
            self.params["text"]=text
        except Exception as e:
            raise RuntimeError(f"BV2 TTS请求失败: {e}")
    
    async def generate_voice(self, text: str):
        if self.client is None:
            self.initialize_client()
        try:
            chunks = []
            async for chunk in self.generate_voice_stream(text):
                chunks.append(chunk)
            return b''.join(chunks)
        except Exception as e:
            raise RuntimeError(f"BV2 TTS请求失败: {e}")

class GPTSoVITSAdapter(_TTSBaseAdapter):
    def __init__(self, api_url: str,params:Optional[dict]=None):
        super().__init__()
        self.api_url = api_url
        self.params= params or models.GPTSoVITSParams(
            prompt_language="zh",
            text_language="zh",
            # "media_type": audio_format, # 支持wav,raw,ogg,aac
            speed_factor=1.0,
            text_split_method="cut0",
            top_k=15,
            top_p=100.0,
            temperature=1.0,
            # "parallel_infer": parallel_infer,
            text=""
        )
    
    def initialize_client(self,gpt_model_path:str,sovits_model_path:str):
        #检测gpt_model_path是否存在
        if not os.path.exists(gpt_model_path):
            raise FileNotFoundError(f"GPT模型文件不存在: {gpt_model_path}")
        
        if not os.path.exists(sovits_model_path):
            raise FileNotFoundError(f"SoVITS模型文件不存在: {sovits_model_path}")
        
        # 检查模型文件扩展名
        if not gpt_model_path.endswith(".ckpt"):
            raise ValueError(f"GPT模型文件扩展名必须为.ckpt: {gpt_model_path}")
        
        if not sovits_model_path.endswith(".pth"):
            raise ValueError(f"SoVITS模型文件扩展名必须为.pth: {sovits_model_path}")
        self.client = AsyncGenerateTTSClient()

    async def generate_voice_stream(self, text:str,**kwargs)->AsyncGenerator[bytes, None]:
        if self.client is None:
            raise RuntimeError("GPTSoVITS客户端未初始化")
        self.update_params(text,**kwargs)
        try:
            sentences = self.client.text_splitter.feed(text)
            for sentence in sentences:
                self.params["text"] = sentence
                async for chunk in self.client.stream(
                    "POST",
                    self.api_url,
                    params=self.params.__dict__
                ):
                    yield chunk
                    await asyncio.sleep(0.01)
            remaining = self.client.text_splitter.flush()
            if remaining.strip():
                self.params["text"]=remaining
                async for chunk in self.client.stream(
                    "POST",
                    self.api_url,
                    params=self.params.__dict__
                ):
                    yield chunk
                    await asyncio.sleep(0.01)
            self.params["text"]=text
        except Exception as e:
            raise RuntimeError(f"GPTSoVITS TTS请求失败: {e}")
    
    async def generate_voice(self, text: str,**kwagrs):
        if self.client is None:
            raise RuntimeError("GPTSoVITS客户端未初始化")
        try:
            chunks = []
            async for chunk in self.generate_voice_stream(text):
                chunks.append(chunk)
            return b''.join(chunks)
        except Exception as e:
            raise RuntimeError(f"GPTSoVITS TTS请求失败: {e}")

class VitsAdapter(_TTSBaseAdapter):
    def __init__(self, api_url: str,params:Optional[dict[str, Union[str, int, float]]]=None):
        super().__init__()
        self.api_url = api_url
        self.params= params or models.VitsParams(
            text="",
            ref_audio_path="",
            prompt_language="zh",
            text_language="zh",
            speed_factor=1.0,
            text_split_method="cut0",
            top_k=15,
            top_p=100.0,
            temperature=1.0,
        )

    async def generate_voice_stream(self,text:str,**kwagrs) -> AsyncGenerator[bytes, None]:
        if self.client is None:
            raise RuntimeError("Vits客户端未初始化")
        self.update_params(text,**kwagrs)
        try:
            sentences = self.client.text_splitter.feed(text)
            for sentence in sentences:
                self.params["text"] = sentence
                async for chunk in self.client.stream(
                    "POST",
                    self.api_url,
                    params=self.params.__dict__
                ):
                    yield chunk
                    await asyncio.sleep(0.01)
            remaining = self.client.text_splitter.flush()
            if remaining.strip():
                self.params["text"]=remaining
                async for chunk in self.client.stream("POST", self.api_url, params=self.params):
                    yield chunk
                    await asyncio.sleep(0.01)
            self.params["text"]=text
            async for chunk in self.client.stream(
                "GET", 
                self.api_url, 
                params=self.params,
                error_message="Vits TTS请求失败"
            ):
                yield chunk
                await asyncio.sleep(0.01)
        except Exception as e:
            raise RuntimeError(f"Vits TTS请求失败: {e}")

    async def generate_voice(self, text: str,**kwagrs):
        if self.client is None:
            raise RuntimeError("Vits客户端未初始化")
        try:
            chunks = []
            async for chunk in self.generate_voice_stream(text):
                chunks.append(chunk)
            return b''.join(chunks)
        except Exception as e:
            raise RuntimeError(f"Vits TTS请求失败: {e}")
