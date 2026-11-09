"""音频：响度统计、分块播放、WAV 解析"""

import asyncio
import time
import wave
from queue import Empty, Full, Queue
from threading import Thread
from typing import Callable, Optional

import numpy as np
from live2d.utils.lipsync import WavHandler as Live2DWavHandler
from pydub import AudioSegment
from pygame import mixer


class _AsyncLoopMixin:
    """异步模式的公共部分。

    核心修复（B22）：loop 与 queue 在**主线程**的 start() 里创建，
    工作线程只负责 set_event_loop + run_until_complete。
    这样 start() 一返回，_loop 就一定可用，push_chunk() 不会再因竞态丢数据。
    """

    def _init_async_resources(self, queue_size: int) -> None:
        self._loop = asyncio.new_event_loop()
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=queue_size)

    def _run_loop(self, worker_coro_factory) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(worker_coro_factory())
        finally:
            try:
                pending = asyncio.all_tasks(self._loop)
                if pending:
                    self._loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            except Exception:
                pass
            try:
                self._loop.close()
            except Exception:
                pass

    def _async_put(self, item) -> None:
        loop = getattr(self, "_loop", None)
        if loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(self._queue.put_nowait, item)
        except (RuntimeError, asyncio.QueueFull):
            pass


class AsyncRmsMeter(_AsyncLoopMixin):
    def __init__(self, is_async: bool = True, sample_width: int = 2, channels: int = 1, queue_size: int = 200):
        self.is_async = is_async
        self.sample_width = sample_width
        self.channels = channels
        self._running = False
        self._latest_rms: float = 0.0
        self._rms: float = 0.0
        self._queue_size = queue_size
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._queue: Optional[object] = None
        self._thread: Optional[Thread] = None

    # 是否更新（自上次取用后 RMS 有变化）
    def update(self) -> bool:
        changed = abs(self._rms - self._latest_rms) > 1e-6
        self._latest_rms = self._rms
        return changed

    def __event_pool(self) -> None:
        self._run_loop(self.__async_worker)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        if self.is_async:
            self._init_async_resources(self._queue_size)
            self._thread = Thread(target=self.__event_pool, name="RmsMeter", daemon=True)
        else:
            self._queue = Queue(maxsize=self._queue_size)
            self._thread = Thread(target=self.__worker, name="RmsMeter", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self.is_async:
            self._async_put(None)  # B26：内部已判空
        else:
            try:
                self._queue.put_nowait(None)  # type: ignore[union-attr]
            except (Full, AttributeError):
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)
        self._thread = None

    def push_chunk(self, chunk: bytes) -> None:
        if not self._running:
            self.start()
        if self.is_async:
            self._async_put(chunk)
        else:
            try:
                self._queue.put_nowait(chunk)  # type: ignore[union-attr]
            except (Full, AttributeError):
                pass

    def get_rms(self) -> float:
        return self._rms

    def set_audio_format(self, sample_width: int, channels: int) -> None:
        self.sample_width = sample_width
        self.channels = channels

    def _compute_rms(self, chunk: bytes) -> Optional[float]:
        """B21：抽成公共实现，同步/异步两条路径都写 _rms。"""
        if self.sample_width != 2 or not chunk:
            return None
        pcm = np.frombuffer(chunk, dtype=np.int16)
        if pcm.size == 0:
            return None
        if self.channels > 1:
            usable = (pcm.size // self.channels) * self.channels
            if usable == 0:
                return None
            pcm = pcm[:usable].reshape(-1, self.channels).mean(axis=1)
        return float(np.sqrt(np.mean(np.square(pcm, dtype=np.float64)))) / 32768.0

    async def __async_worker(self) -> None:
        while self._running:
            try:
                chunk: Optional[bytes] = await self._queue.get()  # type: ignore[union-attr]
            except Empty:
                continue
            if chunk is None:
                break
            rms = self._compute_rms(chunk)
            if rms is not None:
                self._rms = rms  # B21：写的是 get_rms() 会读的那个字段

    def __worker(self) -> None:
        while self._running:
            try:
                chunk = self._queue.get()  # type: ignore[union-attr]
            except Empty:
                continue
            if chunk is None:
                break
            rms = self._compute_rms(chunk)
            if rms is not None:
                self._rms = rms


class AsyncChunkPlayer(_AsyncLoopMixin):
    def __init__(self, queue_size: int = 200, is_async: bool = True) -> None:
        self._thread: Optional[Thread] = None
        self._running = False
        self.is_async = is_async
        self._queue_size = queue_size
        self._before_play_callback: Optional[Callable[[], None]] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._queue: Optional[object] = None

    def __event_pool(self) -> None:
        self._run_loop(self.__async_worker)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        if self.is_async:
            self._init_async_resources(self._queue_size)
            self._thread = Thread(target=self.__event_pool, name="ChunkPlayer", daemon=True)
        else:
            self._queue = Queue(maxsize=self._queue_size)
            self._thread = Thread(target=self.__worker, name="ChunkPlayer", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self.is_async:
            self._async_put(None)
        else:
            try:
                self._queue.put_nowait(None)  # type: ignore[union-attr]
            except (Full, AttributeError):
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)
        self._thread = None

    def push_chunk(self, chunk: bytes) -> None:
        if not self._running:
            self.start()
        if self.is_async:
            self._async_put(chunk)
        else:
            try:
                self._queue.put_nowait(chunk)  # type: ignore[union-attr]
            except (Full, AttributeError):
                pass

    def set_before_play_callback(self, callback: Optional[Callable[[], None]]) -> None:
        self._before_play_callback = callback

    def __play(self, chunk: bytes) -> None:
        if self._before_play_callback:
            self._before_play_callback()
        snd = mixer.Sound(buffer=chunk)
        channel = mixer.Channel(0)
        channel.play(snd)
        while channel.get_busy() and self._running:
            time.sleep(0.005)

    def __worker(self) -> None:
        while self._running:
            try:
                chunk = self._queue.get()  # type: ignore[union-attr]
            except Empty:
                continue
            if chunk is None:
                break
            if not chunk:
                continue
            try:
                self.__play(chunk)
            except Exception:
                continue

    async def __async_worker(self) -> None:
        while self._running:
            try:
                chunk = await self._queue.get()  # type: ignore[union-attr]
            except Empty:
                continue
            if chunk is None:
                break
            if not chunk:
                continue
            try:
                if self._before_play_callback:
                    self._before_play_callback()
                snd = mixer.Sound(buffer=chunk)
                channel = mixer.Channel(0)
                channel.play(snd)
                # B23：async worker 里绝不能用 time.sleep，否则整个 loop 停摆，
                # 播放期间 push_chunk 排不上队，队列满后 chunk 被丢弃 -> 声音断续
                while channel.get_busy() and self._running:
                    await asyncio.sleep(0.005)
            except Exception:
                continue


class WavHandler(Live2DWavHandler):
    def __init__(self) -> None:
        super().__init__()
        self.pcmData: Optional[np.ndarray] = None

    def Start(self, filePath: str) -> None:
        self.ReleasePcmData()
        try:
            if filePath.endswith(".wav"):
                with wave.open(filePath, "r") as wav:
                    self.numFrames = wav.getnframes()
                    self.sampleRate = wav.getframerate()
                    self.sampleWidth = wav.getsampwidth()
                    self.numChannels = wav.getnchannels()
                    self.pcmData = np.frombuffer(
                        wav.readframes(self.numFrames), dtype=np.int16
                    )
            else:
                audio = AudioSegment.from_file(filePath)
                self.numFrames = int(audio.frame_count(ms=len(audio)))
                self.sampleRate = audio.frame_rate
                self.sampleWidth = audio.sample_width
                self.numChannels = audio.channels
                self.pcmData = np.frombuffer(audio.raw_data, dtype=np.int16)

            if self.pcmData is None or self.pcmData.size == 0:
                self.ReleasePcmData()
                return

            # B24：静音音频 np.max 为 0，直接除会得 nan
            peak = float(np.max(np.abs(self.pcmData)))
            if peak > 1e-8:
                self.pcmData = self.pcmData / peak

            # 声道数整除不了就截断，避免 reshape 抛错
            usable = (self.pcmData.size // self.numChannels) * self.numChannels
            if usable <= 0:
                self.ReleasePcmData()
                return
            self.pcmData = self.pcmData[:usable].reshape(-1, self.numChannels).T
            self.startTime = time.time()
            self.lastOffset = 0
        except Exception:
            self.ReleasePcmData()

    def Start_Pcm(self, pcm: np.ndarray) -> None:
        """B25：父类 Update() 依赖 numFrames/sampleRate/numChannels 等字段，
        原来一个都没设，Update() 里会直接炸。"""
        self.ReleasePcmData()
        if pcm is None or pcm.size == 0:
            return
        self.pcmData = pcm
        self.numChannels = 1 if pcm.ndim == 1 else pcm.shape[0]
        self.numFrames = pcm.shape[-1]
        self.sampleRate = getattr(self, "sampleRate", 16000) or 16000
        self.sampleWidth = 2
        self.startTime = time.time()
        self.lastOffset = 0
