"""TTS Shim：文本分句 → 供应商音频流。

修复：``TextSplitter`` 是实例状态，旧实现跨请求复用同一个 buffer，上一次
没凑够一句的尾巴会粘到下一次合成里；现在每轮合成前显式 reset。
"""
from __future__ import annotations

import base64
from typing import Any, AsyncGenerator, Dict, List

from .base import _ShimBase


class TextSplitter:
    """按句子边界切分，避免把整段话一次性发给 TTS 造成首包延迟。"""

    def __init__(self, max_chars: int = 50):
        self.max_chars = max_chars
        self._buffer = ""
        self._sentence_endings = set("。！？.!?\n")
        self._punctuation = set("，,、；;：: ")

    def reset(self) -> None:
        self._buffer = ""

    def feed(self, text: str) -> List[str]:
        self._buffer += text
        sentences: List[str] = []
        while len(self._buffer) >= self.max_chars:
            cut_pos = -1
            for i in range(self.max_chars - 1, -1, -1):
                if self._buffer[i] in self._sentence_endings:
                    cut_pos = i + 1
                    break
            if cut_pos == -1:
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


class TTSShim(_ShimBase):
    capability = "tts"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    def _protocol(self) -> str:
        return str(self.endpoint.get("protocol") or "generic").lower()

    def _path_params(self, extra: Dict[str, Any]) -> Dict[str, str]:
        params = self.request_params(extra)
        out: Dict[str, str] = {}
        # ElevenLabs 等把 voice_id 放在路径里
        voice_id = params.get("voice_id")
        if voice_id:
            out["voice_id"] = str(voice_id)
        return out

    def initialize_client(self, **kwargs: Any) -> "TTSShim":
        # 端点 / 凭据 / 请求参数的归类统一由 _ShimBase 处理，避免此处
        # 漏掉自定义 auth.field 或把密钥当成请求参数。
        super().initialize_client(**kwargs)
        return self

    def _audio_payload(self, text: str, extra: Dict[str, Any]) -> Dict[str, Any]:
        params = self.request_params(extra)
        for key in self._path_params(extra):   # 路径参数不再重复进 body
            params.pop(key, None)
        return {"text": text, **params}
    
    async def _synth_sentence(self, text: str, extra: Dict[str, Any]) -> AsyncGenerator[bytes, None]:
        protocol = self._protocol()
        if protocol == "azure_ssml":
            async for chunk in self._synth_azure(text, extra):
                yield chunk
            return
        if protocol == "google_tts":
            async for chunk in self._synth_google(text, extra):
                yield chunk
            return
        payload = self._audio_payload(text, extra)
        async for chunk in self._ensure_transport().stream_bytes(
            payload, 
            path_params=self._path_params(extra)
        ):
            yield chunk

    async def _synth_azure(self, text: str, extra: Dict[str, Any]) -> AsyncGenerator[bytes, None]:
        import httpx
        params = self.request_params(extra)
        voice = str(params.get("voice_name") or "zh-CN-XiaoxiaoNeural")
        lang = str(params.get("language") or "zh-CN")
        output_format = str(params.get("output_format") or "audio-16khz-128kbitrate-mono-mp3")
        ssml = (
            f'<speak version="1.0" xml:lang="{lang}">'
            f'<voice name="{voice}">{text}</voice></speak>'
        )
        transport = self._ensure_transport()
        headers = transport._headers()
        headers["Content-Type"] = "application/ssml+xml"
        headers["X-Microsoft-OutputFormat"] = output_format
        client = transport._client_or_raise()
        async with client.stream(
            "POST", transport.build_url(), content=ssml.encode("utf-8"), headers=headers
        ) as resp:
            resp.raise_for_status()
            async for chunk in resp.aiter_bytes():
                if chunk:
                    yield chunk

    async def generate_voice_stream(
        self, 
        text: str,
        **kwargs: Any
    ) -> AsyncGenerator[bytes, None]:
        splitter = TextSplitter(max_chars=30)
        for sentence in splitter.feed(text):
            async for chunk in self._synth_sentence(sentence, kwargs):
                yield chunk
        tail = splitter.flush()
        if tail.strip():
            async for chunk in self._synth_sentence(tail, kwargs):
                yield chunk

    async def _synth_google(self, text: str, extra: Dict[str, Any]) -> AsyncGenerator[bytes, None]:
        params = self.request_params(extra)
        payload = {
            "input": {"text": text},
            "voice": {
                "languageCode": params.get("language_code", "cmn-CN"),
                "name": params.get("voice_name"),
            },
            "audioConfig": {"audioEncoding": params.get("audio_encoding", "MP3")},
        }
        data = await self._ensure_transport().request_json(payload)
        b64 = data.get("audioContent")
        if b64:
            yield base64.b64decode(b64)

    async def generate_voice(self, text: str, **kwargs: Any) -> bytes:
        buf: List[bytes] = []
        async for chunk in self.generate_voice_stream(text, **kwargs):
            buf.append(chunk)
        return b"".join(buf)

    def get_audio_format(self) -> str:
        value = self.params.get("audio_format", "wav")
        return str(value or "wav")

    def get_audio_sample_rate(self) -> int:
        return 44100

    def get_audio_channels(self) -> int:
        return 1

    def get_audio_sample_width(self) -> int:
        return 2

    def get_params(self) -> Dict[str, Any]:
        return dict(self.params)
