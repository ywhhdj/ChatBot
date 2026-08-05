from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import List, Optional, Tuple

from pydub import AudioSegment


@dataclass
class AudioFormat:
    sample_rate: int = 44100
    channels: int = 1
    sample_width: int = 2  # bytes, 2 => 16-bit PCM


class AudioStreamDecoder:
    """
    简易流式解码器：
    - WAV: 解析 header 后直接输出 PCM
    - MP3: 缓冲到一定大小后整体解码为 PCM
    """

    def __init__(self, fmt: str) -> None:
        self.fmt = (fmt or "wav").lower()
        self._buffer = bytearray()
        self._wav_header_parsed = False
        self._audio_format = AudioFormat()

    def get_format(self) -> AudioFormat:
        return self._audio_format

    def feed(self, chunk: bytes) -> List[bytes]:
        if not chunk:
            return []
        if self.fmt == "wav":
            return self._feed_wav(chunk)
        if self.fmt == "mp3":
            return self._feed_mp3(chunk)
        # 默认按 WAV 处理
        return self._feed_wav(chunk)

    def _feed_wav(self, chunk: bytes) -> List[bytes]:
        self._buffer.extend(chunk)
        if not self._wav_header_parsed:
            parsed = self._try_parse_wav_header()
            if not parsed:
                return []
        if not self._buffer:
            return []
        pcm = bytes(self._buffer)
        self._buffer.clear()
        return [pcm]

    def _try_parse_wav_header(self) -> bool:
        buf = self._buffer
        if len(buf) < 44:
            return False
        if buf[0:4] != b"RIFF" or buf[8:12] != b"WAVE":
            return False

        fmt_idx = buf.find(b"fmt ")
        data_idx = buf.find(b"data")
        if fmt_idx == -1 or data_idx == -1:
            return False
        if len(buf) < fmt_idx + 24 or len(buf) < data_idx + 8:
            return False

        channels = int.from_bytes(buf[fmt_idx + 10:fmt_idx + 12], "little", signed=False)
        sample_rate = int.from_bytes(buf[fmt_idx + 12:fmt_idx + 16], "little", signed=False)
        bits = int.from_bytes(buf[fmt_idx + 22:fmt_idx + 24], "little", signed=False)
        sample_width = max(1, bits // 8)

        data_offset = data_idx + 8
        if len(buf) < data_offset:
            return False

        self._audio_format = AudioFormat(sample_rate=sample_rate, channels=channels, sample_width=sample_width)
        self._buffer = bytearray(buf[data_offset:])
        self._wav_header_parsed = True
        return True

    def _feed_mp3(self, chunk: bytes) -> List[bytes]:
        self._buffer.extend(chunk)
        # mp3 需要缓冲一定大小再解码
        if len(self._buffer) < 64 * 1024:
            return []
        return self._decode_mp3_buffer()

    def flush(self) -> List[bytes]:
        if self.fmt == "mp3" and self._buffer:
            return self._decode_mp3_buffer()
        if self.fmt == "wav" and self._buffer:
            pcm = bytes(self._buffer)
            self._buffer.clear()
            return [pcm]
        return []

    def _decode_mp3_buffer(self) -> List[bytes]:
        try:
            audio = AudioSegment.from_file(BytesIO(self._buffer), format="mp3")
        except Exception:
            return []
        self._audio_format = AudioFormat(
            sample_rate=audio.frame_rate,
            channels=audio.channels,
            sample_width=audio.sample_width,
        )
        raw = audio.raw_data
        self._buffer.clear()
        return [raw] if raw else []
