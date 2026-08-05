from threading import Thread
import asyncio
from typing import Optional
import wave
from queue import Queue,Empty
import numpy as np
import time
from typing import Callable
from live2d.utils.lipsync import WavHandler as Live2DWavHandler
from pydub import AudioSegment
from pygame import mixer

class AsyncRmsMeter:
    def __init__(self, is_async: bool = True, sample_width: int = 2, channels: int = 1, queue_size: int = 200):
        self.is_async = is_async
        self.sample_width = sample_width
        self.channels = channels
        self._running = False
        self._latest_rms: float = 0.0
        self._rms: float = 0.0
        self._queue_size = queue_size
        if not self.is_async:
            self._queue: Queue[Optional[bytes]] = Queue(maxsize=self._queue_size) # type: ignore
        self._thread: Optional[Thread] = None

    #获取是否更新
    def update(self):
        return abs(self._rms - self._latest_rms) > 1e-10

    def __event_pool(self):
        if self.is_async:
            self._loop = asyncio.new_event_loop()
            self._queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue(maxsize=self._queue_size) # type: ignore
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self.__async_worker())
        finally:
            padding=asyncio.all_tasks(self._loop)
            self._loop.run_until_complete(asyncio.gather(*padding,return_exceptions=True))
            self._loop.close()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        if self.is_async:
            self._thread = Thread(target=self.__event_pool)
        else:
            self._thread = Thread(target=self.__worker)
        self._thread.start()

    def stop(self):
        self._running = False
        try:
            if self.is_async:
                self._loop.call_soon_threadsafe(self._queue.put_nowait, None)
            else:
                self._queue.put_nowait(None)
        except asyncio.QueueFull:
            pass
        except Exception:
            pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)
        self._thread = None

    def push_chunk(self, chunk: bytes) -> None:
        if not self._running:
            self.start()
        try:
            if self.is_async:
                self._loop.call_soon_threadsafe(self._queue.put_nowait, chunk)
            else:
                self._queue.put_nowait(chunk)
        except asyncio.QueueFull:
            pass
        except Exception:
            pass

    def get_rms(self) -> float:
        return self._rms

    def set_audio_format(self, sample_width: int, channels: int) -> None:
        self.sample_width = sample_width
        self.channels = channels
    
    async def __async_worker(self):
        while self._running:
            try:
                chunk:bytes = await self._queue.get() #type:ignore
            except Empty:
                continue
            if chunk is None:
                break
            if self.sample_width != 2 or not chunk:
                continue
            pcm = np.frombuffer(chunk, dtype=np.int16)
            if pcm.size == 0:
                continue
            if self.channels > 1:
                pcm = pcm.reshape(-1, self.channels).mean(axis=1)
            rms = float(np.sqrt(np.mean(np.square(pcm))))
            self._latest_rms = rms / 32768.0

    def __worker(self) -> None:
        while self._running:
            self._latest_rms = self._rms
            try:
                chunk = self._queue.get()
            except Empty:
                continue
            if chunk is None:
                break
            if not chunk:
                continue
            # 仅支持16-bit PCM
            if self.sample_width != 2:
                continue
            pcm = np.frombuffer(chunk, dtype=np.int16) # type: ignore
            if pcm.size == 0:
                continue
            if self.channels > 1:
                pcm = pcm.reshape(-1, self.channels).mean(axis=1)
            rms = float(np.sqrt(np.mean(np.square(pcm))))
            self._rms = rms / 32768.0

class AsyncChunkPlayer:
    def __init__(self, queue_size: int = 200, is_async: bool = True) -> None:
        self._thread: Optional[Thread] = None
        self._running = False
        self.is_async = is_async
        self._queue_size = queue_size
        self._before_play_callback: Optional[Callable[[], None]] = None
        if not is_async:
            self._queue: Queue[Optional[bytes]] = Queue(maxsize=queue_size) # type: ignore
    
    def __event_pool(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        if self.is_async:
            self._queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue(maxsize=self._queue_size) # type: ignore
        try:
            self._loop.run_until_complete(self.__async_worker())
        finally:
            pending = asyncio.all_tasks(self._loop)
            self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self._loop.close()
            

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        if self.is_async:
            self._thread = Thread(target=self.__event_pool)
        else:
            self._thread = Thread(target=self.__worker)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        try:
            if self.is_async:
                self._loop.call_soon_threadsafe(self._queue.put_nowait, None)
            else:
                self._queue.put_nowait(None)
        except asyncio.QueueFull:
            pass
        except Exception:
            pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)
        self._thread = None

    def push_chunk(self, chunk: bytes) -> None:
        if not self._running:
            self.start()
        try:
            if self.is_async:
                self._loop.call_soon_threadsafe(self._queue.put_nowait, chunk)
            else:
                self._queue.put_nowait(chunk)
        except Exception:
            pass

    def set_before_play_callback(self, callback: Optional[Callable[[], None]]) -> None:
        self._before_play_callback = callback

    def __worker(self) -> None:
        channel = mixer.Channel(0)
        while self._running:
            try:
                chunk = self._queue.get()
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
                channel.play(snd)
                while channel.get_busy() and self._running:
                    time.sleep(0.005)
            except Exception:
                continue
    
    async def __async_worker(self) -> None:
        channel = mixer.Channel(0)
        while self._running:
            try:
                chunk = await self._queue.get() #type:ignore
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
                channel.play(snd)
                while channel.get_busy() and self._running:
                    time.sleep(0.005)
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
                try:
                    with wave.open(filePath, "r") as wav:
                        self.numFrames = wav.getnframes()
                        self.sampleRate = wav.getframerate()
                        self.sampleWidth = wav.getsampwidth()
                        self.numChannels = wav.getnchannels()
                        self.pcmData = np.frombuffer(wav.readframes(self.numFrames), dtype=np.int16)
                except Exception:
                    self.ReleasePcmData()
            else:
                audio=AudioSegment.from_file(filePath)
                self.numFrames = int(audio.frame_count(ms=len(audio)))
                self.sampleRate = audio.frame_rate
                self.sampleWidth = audio.sample_width
                self.numChannels = audio.channels
                self.pcmData = np.frombuffer(audio.raw_data, dtype=np.int16)
            self.pcmData = self.pcmData / np.max(np.abs(self.pcmData)) # type: ignore
            self.pcmData = self.pcmData.reshape(-1, self.numChannels).T #type: ignore
            self.startTime = time.time()
            self.lastOffset = 0
        except Exception:
            self.ReleasePcmData()
    
    def Start_Pcm(self,pcm:np.ndarray) -> None:
        self.ReleasePcmData()
        self.pcmData = pcm
        self.startTime = time.time()
        self.lastOffset = 0
