"""faster-whisper 本地 ASR 运行时"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from ..base import BaseRuntime


def _np():
    import numpy as np
    return np


class FasterWhisperRuntime(BaseRuntime):
    def __init__(self, endpoint):
        super().__init__(endpoint)
        self.model = None
        self.language = endpoint.get("language", "zh")
        self.beam_size = int(endpoint.get("beam_size", 5))
        self.sample_rate = int(endpoint.get("sample_rate", 16000))
        self._audio_buffer = None
        self._text_buffer = ""

    async def _load(self):
        from faster_whisper import WhisperModel

        model_dir = self.endpoint.get("model_dir") or self.endpoint.get("model_size", "base")
        device = self.endpoint.get("device", "auto")
        loop = asyncio.get_event_loop()
        self.model = await loop.run_in_executor(
            None, lambda: WhisperModel(model_dir, device=device)
        )

    async def _infer(self, payload):
        return await self.transcribe(payload)

    async def transcribe(self, payload: dict) -> str:
        await self.ensure_loaded()
        np = _np()
        audio = np.frombuffer(payload["audio"], dtype=np.int16).astype(np.float32) / 32768.0
        loop = asyncio.get_event_loop()
        segs, _ = await loop.run_in_executor(
            None,
            lambda: self.model.transcribe(  # type:ignore
                audio,
                language=payload.get("language", self.language),
                beam_size=int(payload.get("beam_size", self.beam_size)),
            ),
        )
        return "".join(s.text for s in segs)

    async def transcribe_stream(self, payload: dict) -> AsyncGenerator[str, None]:
        await self.ensure_loaded()
        np = _np()
        if self._audio_buffer is None:
            self._audio_buffer = np.array([], dtype=np.float32)
        audio = np.frombuffer(payload["audio"], dtype=np.int16).astype(np.float32) / 32768.0
        self._audio_buffer = np.concatenate([self._audio_buffer, audio])
        if len(self._audio_buffer) < self.sample_rate * 0.5 and not payload.get("is_final"):
            return
        loop = asyncio.get_event_loop()
        segs, _ = await loop.run_in_executor(
            None,
            lambda: self.model.transcribe(  # type:ignore
                self._audio_buffer.copy(), #type: ignore
                language=payload.get("language", self.language),
                beam_size=int(payload.get("beam_size", self.beam_size)),
            ),
        )
        new = "".join(s.text for s in segs).strip()
        if new and new not in self._text_buffer:
            self._text_buffer += new
            yield new
        if payload.get("is_final"):
            self._audio_buffer = np.array([], dtype=np.float32)
            self._text_buffer = ""
        else:
            keep = int(self.sample_rate * 0.5)
            if len(self._audio_buffer) > keep:
                self._audio_buffer = self._audio_buffer[-keep:]

    def close(self):
        if self.model is not None:
            self.model = None
            try:
                import torch
                torch.cuda.empty_cache()
            except Exception:  # noqa: BLE001
                pass
        self._audio_buffer = None
        self._text_buffer = ""
        super().close()
