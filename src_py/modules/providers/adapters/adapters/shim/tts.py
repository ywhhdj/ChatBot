from typing import List

from ...adapters.shim.base import _ShimBase

class TextSplitter:
    """智能文本分割器，用于流式TTS"""
    
    def __init__(self, max_chars: int = 50):
        self.max_chars = max_chars
        self._buffer = ""
        self._sentence_endings = set('。！？.!?\n')
        self._punctuation = set('，,、；;：: ')
    
    def feed(self, text: str) -> List[str]:
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

class TTSShim(_ShimBase):
    capability = "tts"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._splitter = TextSplitter(max_chars=30)
        self._transport = None

    def initialize_client(self, **kwargs):
        self.init_params.update(kwargs)
        self._transport = self._ensure_transport()[0]
        return self

    def _params(self, extra):
        return {**self._cfg.get("params", {}), **self.init_params, **extra}

    async def generate_voice_stream(self, text, **kwargs):
        http, _ = self._ensure_transport()
        ep = self._cfg["endpoint"]
        params = self._params(kwargs)
        for sentence in self._splitter.feed(text):
            async for chunk in http.stream(ep, {"text": sentence, **params}, self.secrets):
                yield chunk
        tail = self._splitter.flush()
        if tail.strip():
            async for chunk in http.stream(ep, {"text": tail, **params}, self.secrets):
                yield chunk

    async def generate_voice(self, text, **kwargs):
        buf = []
        async for c in self.generate_voice_stream(text, **kwargs):
            buf.append(c)
        return b"".join(buf)

    def get_audio_format(self):
        spec = self._cfg.get("params", {}).get("audio_format", {})
        return spec.get("default", "wav") if isinstance(spec, dict) else "wav"

    def get_audio_sample_rate(self): return 44100
    def get_audio_channels(self): return 1
    def get_audio_sample_width(self): return 2
    def get_params(self): return self._params({})

    def close(self):
        self._transport = None
        super().close()