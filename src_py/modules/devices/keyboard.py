try:
    from pynput import keyboard
    from pyaudio import PyAudio, paInt16
except:
    raise ImportError("pynput and pyaudio is required for keyboard device")
import asyncio
from concurrent.futures import ThreadPoolExecutor
import io
from typing import Callable, Optional
import wave

from .. import events
from .base import BaseDevice

class StreamingAudioRecorder:
    def __init__(
            self, 
            format=paInt16, 
            channels=1, 
            rate=16000, 
            chunk=1024,
            segment_duration_ms: int = 200
        ):  # 每200ms推送一次音频片段
        self.format = format
        self.channels = channels
        self.rate = rate
        self.chunk = chunk
        self.segment_samples = int(rate * segment_duration_ms / 1000)  # 每个片段的采样数
        self.audio = PyAudio()
        self.frames = []
        self.is_recording = False
        self.stream = None
        self._on_audio_segment: Optional[Callable] = None  # 音频片段回调
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_on_audio_segment(self, callback: Callable[[bytes], None]):
        self._on_audio_segment = callback

    def start_recording(self):
        """开始录音，并在循环中实时推送音频片段"""
        self.frames = []
        self.is_recording = True
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self.stream = self.audio.open(
            format=self.format,
            channels=self.channels,
            rate=self.rate,
            input=True,
            frames_per_buffer=self.chunk
        )
        segment_buffer = []
        current_samples = 0
        
        while self.is_recording:
            data = self.stream.read(self.chunk)
            self.frames.append(data)
            segment_buffer.append(data)
            current_samples += len(data) // 2  # 16bit = 2 bytes per sample
            # 达到片段长度，推送
            if current_samples >= self.segment_samples:
                segment_data = b''.join(segment_buffer)
                if self._on_audio_segment:
                    # 将片段转为WAV格式
                    wav_segment = self._to_wav_bytes(segment_data)
                    self._on_audio_segment(wav_segment)
                segment_buffer = []
                current_samples = 0
        # 推送剩余数据
        if segment_buffer:
            segment_data = b''.join(segment_buffer)
            if self._on_audio_segment:
                wav_segment = self._to_wav_bytes(segment_data)
                self._on_audio_segment(wav_segment)

    def stop_recording(self) -> bytes:
        self.is_recording = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self._loop:
            self._loop.close()
        return self._to_wav_bytes(b''.join(self.frames))

    def _to_wav_bytes(self, audio_data: bytes) -> bytes:
        """将原始音频数据转为WAV格式"""
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(self.audio.get_sample_size(self.format))
            wf.setframerate(self.rate)
            wf.writeframes(audio_data)
        return buffer.getvalue()

@events.on_event_class([
    (events.types.AppEventType.KeyboardEventType.KEYBOARD_START, "start"),
    (events.types.AppEventType.KeyboardEventType.KEYBOARD_STOP, "stop")
])
class KeyboardDevice(BaseDevice):
    def __init__(self, key: Optional[dict[str,str]] = {
        "interrupt_key":"esc"
    }):
        if not key:
            return
        super().__init__("keyboard", "Keyboard Device")
        self.audio_recorder = StreamingAudioRecorder()
        self.is_pressing = False
        self.hotkeys = {k: self.get_key(k) for k in key.keys()}
        self.keyboard_thread = ThreadPoolExecutor(max_workers=2) #处理按键的线程池
    #将str转换为按键
    def get_key(self, key_str: str):
        keys={
            "esc": keyboard.Key.esc,
            "enter": keyboard.Key.enter,
            "space": keyboard.Key.space,
            "backspace": keyboard.Key.backspace,
            "tab": keyboard.Key.tab,
            "shift": keyboard.Key.shift,
            "ctrl": keyboard.Key.ctrl,
            "alt": keyboard.Key.alt,
            "caps_lock": keyboard.Key.caps_lock,
        }
        # if "+" in key_str:
        #     key_str = key_str.split("+")
        #     keys = [self.get_key(k) for k in key_str]
        #     return keys
        return keys.get(key_str, None)

    def on_press(self, key):
        if self.hotkeys["record_key"] == key:
            self.is_pressing = True
            print(f"{self.hotkeys['record_key']} pressed")
            self.keyboard_thread.submit(self.audio_recorder.start_recording)
    
    def on_release(self, key):
        if self.hotkeys["record_key"] == key:
            self.is_pressing = False
            print(f"{self.hotkeys['record_key']} released")
            self.keyboard_thread.submit(self.audio_recorder.stop_recording)
        if self.hotkeys["interrupt_key"] == key:
            is_interrupting = True
            
    
    def start(self):
        with keyboard.Listener(on_press=self.on_press, on_release=self.on_release) as listener:
            listener.join()
    
    def stop(self):
        self.is_pressing = False
        self.keyboard_thread.shutdown(wait=True)
        self.audio_recorder.stop_recording()
