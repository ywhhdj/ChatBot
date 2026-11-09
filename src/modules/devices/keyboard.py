"""键盘设备：把后端热键映射应用到系统级按键监听。"""

from __future__ import annotations

import io
import threading
import wave
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional, Set, Tuple

from .. import events
from .base import BaseDevice
from .hotkeys import (
    MODIFIER_ORDER,
    get_hotkey_registry,
    normalize_combo,
)

# pynput / pyaudio 是可选的系统级依赖：延迟导入，缺依赖时仍能加载模块与查询映射。
def _require_keyboard():
    try:
        from pynput import keyboard
        return keyboard
    except ImportError as exc:  # pragma: no cover - 取决于部署环境
        raise RuntimeError("键盘监听需要 pynput") from exc


def _require_audio():
    try:
        from pyaudio import PyAudio, paInt16
        return PyAudio, paInt16
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("录音需要 pyaudio") from exc


class StreamingAudioRecorder:
    """按 200ms 切片推送音频片段，并保留完整录音用于说话人识别等场景。"""

    def __init__(
        self,
        channels: int = 1,
        rate: int = 16000,
        chunk: int = 1024,
        segment_duration_ms: int = 200,
        audio: Any = None,
        format: Any = None,
    ) -> None:
        PyAudio, paInt16 = _require_audio()
        self.format = format if format is not None else paInt16
        self.channels = channels
        self.rate = rate
        self.chunk = chunk
        self.segment_samples = int(rate * segment_duration_ms / 1000)
        self.audio = audio if audio is not None else PyAudio()
        self.frames: list[bytes] = []
        self.is_recording = False
        self.stream = None
        self._on_audio_segment: Optional[Callable[[bytes], None]] = None
        self._lock = threading.Lock()

    def set_on_audio_segment(self, callback: Callable[[bytes], None]) -> None:
        self._on_audio_segment = callback

    def start_recording(self) -> None:
        """阻塞式采集循环；由设备的单线程 executor 串行执行。"""
        with self._lock:
            if self.is_recording:
                return
            self.frames = []
            self.is_recording = True
            self.stream = self.audio.open(
                format=self.format,
                channels=self.channels,
                rate=self.rate,
                input=True,
                frames_per_buffer=self.chunk,
            )
        segment_buffer: list[bytes] = []
        current_samples = 0
        try:
            while self.is_recording:
                data = self.stream.read(self.chunk)
                with self._lock:
                    self.frames.append(data)
                segment_buffer.append(data)
                current_samples += len(data) // 2
                if current_samples >= self.segment_samples:
                    self._push(b"".join(segment_buffer))
                    segment_buffer = []
                    current_samples = 0
            if segment_buffer:
                self._push(b"".join(segment_buffer))
        finally:
            with self._lock:
                self.is_recording = False
                if self.stream is not None:
                    try:
                        self.stream.stop_stream()
                        self.stream.close()
                    except Exception:  # noqa: BLE001
                        pass
                    self.stream = None

    def _push(self, segment: bytes) -> None:
        if self._on_audio_segment is None:
            return
        try:
            self._on_audio_segment(self._to_wav_bytes(segment))
        except Exception:  # noqa: BLE001 - 回调失败不影响采集
            pass

    def stop_recording(self) -> bytes:
        """请求停止并返回完整 WAV；不会与 start 抢线程池。"""
        with self._lock:
            self.is_recording = False
            frames = list(self.frames)
        return self._to_wav_bytes(b"".join(frames))

    def _to_wav_bytes(self, audio_data: bytes) -> bytes:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(self.audio.get_sample_size(self.format))
            wf.setframerate(self.rate)
            wf.writeframes(audio_data)
        return buffer.getvalue()


@events.on_event_class([
    (events.types.AppEventType.KeyboardEventType.KEYBOARD_START, "start"),
    (events.types.AppEventType.KeyboardEventType.KEYBOARD_STOP, "stop"),
])
class KeyboardDevice(BaseDevice):
    """系统级热键监听。动作执行由上层通过 bind_action_handler 注入。"""

    _MODIFIER_NAMES = {
        "ctrl": "Ctrl", 
        "ctrl_l": "Ctrl",
        "ctrl_r": "Ctrl",
        "alt": "Alt",
        "alt_l": "Alt",
        "alt_gr": "Alt",
        "alt_r": "Alt",
        "shift": "Shift",
        "shift_l": "Shift",
        "shift_r": "Shift",
        "cmd": "Meta",
        "cmd_l": "Meta",
        "cmd_r": "Meta",
        "windows": "Meta",
        "super": "Meta",
    }
    _PRIMARY_NAMES = {
        "esc": "Esc", 
        "enter": "Enter",
        "space": "Space",
        "backspace": "Backspace",
        "tab": "Tab",
        "delete": "Delete",
        "insert": "Insert",
        "home": "Home",
        "end": "End",
        "page_up": "PageUp",
        "page_down": "PageDown",
        "caps_lock": "CapsLock",
        "up": "Up",
        "down": "Down",
        "left": "Left",
        "right": "Right",
        "print_screen": "PrintScreen",
        "scroll_lock": "ScrollLock",
        "pause": "Pause",
    }

    def __init__(self, registry: Any = None, audio_recorder: Any = None) -> None:
        super().__init__("keyboard", "Keyboard Device")
        self.registry = registry if registry is not None else get_hotkey_registry()
        self.audio_recorder = audio_recorder
        self._pressed_modifiers: Set[str] = set()
        self._hold_by_primary: Dict[str, str] = {}
        self._active_holds: Set[str] = set()
        self._handlers: Dict[str, Callable[[str, str], None]] = {}
        self._listener: Any = None
        # 单线程：start_recording 是长循环，stop 必须排在它之后执行
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kbd")
        self._record_future: Optional[Future] = None
        self._lock = threading.RLock()
        self._combo_map: Dict[str, Tuple[str, str]] = {}
        self.reload()
        self.registry.subscribe(self.reload)

    # ---------- 映射 ----------

    def reload(self, registry: Any = None) -> None:
        """注册表变更后重建反查表；设备无需重启。"""
        reg = registry if registry is not None else self.registry
        bindings = reg.bindings() if hasattr(reg, "bindings") else {}
        modes = {}
        if hasattr(reg, "describe"):
            try:
                modes = {
                    a["id"]: a.get("mode", "press") 
                    for a in reg.describe()["actions"]
                }
            except Exception:  # noqa: BLE001
                modes = {}
        mapping: Dict[str, Tuple[str, str]] = {}
        for action, combo in bindings.items():
            if not combo:
                continue
            try:
                normalized = normalize_combo(combo)
            except Exception:  # noqa: BLE001
                continue
            mapping[normalized] = (action, modes.get(action, "press"))
        with self._lock:
            self._combo_map = mapping

    def bind_action_handler(
        self, action: str, handler: Callable[[str, str], None]
    ) -> None:
        """注册动作回调：handler(action_id, phase)，phase ∈ press/start/end。"""
        with self._lock:
            self._handlers[action] = handler

    # ---------- 按键解析 ----------

    def _key_token(self, key: Any) -> Tuple[str, str]:
        """返回 (kind, token)，kind ∈ modifier/primary/empty。"""
        name = getattr(key, "name", None)
        if name:
            low = str(name).lower()
            if low in self._MODIFIER_NAMES:
                return "modifier", self._MODIFIER_NAMES[low]
            if low in self._PRIMARY_NAMES:
                return "primary", self._PRIMARY_NAMES[low]
            if low.startswith("f") and low[1:].isdigit():
                return "primary", low.upper()
            return "empty", ""
        char = getattr(key, "char", None)
        if char:
            return "primary", str(char)
        return "empty", ""

    def _combo_for(self, primary: str) -> str:
        ordered = [m for m in MODIFIER_ORDER if m in self._pressed_modifiers]
        try:
            return normalize_combo("+".join(ordered + [primary]))
        except Exception:  # noqa: BLE001
            return ""

    # ---------- 监听 ----------

    def on_press(self, key: Any) -> None:
        kind, token = self._key_token(key)
        if kind == "modifier":
            self._pressed_modifiers.add(token)
            return
        if kind != "primary":
            return
        combo = self._combo_for(token)
        with self._lock:
            hit = self._combo_map.get(combo)
        if hit is None:
            return
        action, mode = hit
        if mode == "hold":
            with self._lock:
                if action in self._active_holds:
                    return
                self._active_holds.add(action)
                self._hold_by_primary[token] = action
            self._dispatch(action, "start")
        else:
            self._dispatch(action, "press")

    def on_release(self, key: Any) -> None:
        kind, token = self._key_token(key)
        if kind == "modifier":
            self._pressed_modifiers.discard(token)
            return
        if kind != "primary":
            return
        with self._lock:
            action = self._hold_by_primary.pop(token, None)
            if action:
                self._active_holds.discard(action)
        if action:
            self._dispatch(action, "end")

    def _dispatch(self, action: str, phase: str) -> None:
        with self._lock:
            handler = self._handlers.get(action)
        if handler is not None:
            try:
                handler(action, phase)
                return
            except Exception:  # noqa: BLE001
                from ..logger import logger
                logger.warning(f"[Keyboard] 动作 {action} 回调失败")
                return
        if action == "record":
            self._default_record(action, phase)
        else:
            from ..logger import logger
            logger.debug(f"[Keyboard] 动作 {action}({phase}) 未绑定处理器")

    def _default_record(self, action: str, phase: str) -> None:
        if phase == "start":
            if self.audio_recorder is None:
                try:
                    self.audio_recorder = StreamingAudioRecorder()
                except RuntimeError as exc:
                    from ..logger import logger
                    logger.warning(f"[Keyboard] 录音不可用: {exc}")
                    return
            self._record_future = self._executor.submit(
                self.audio_recorder.start_recording
            )
        elif phase == "end" and self.audio_recorder is not None:
            # 同一个单线程 executor：stop 一定排在 start 之后，不再乱序。
            future = self._executor.submit(self.audio_recorder.stop_recording)
            try:
                wav = future.result(timeout=5.0)
            except Exception:  # noqa: BLE001
                wav = b""
            from ..logger import logger
            logger.debug(f"[Keyboard] 录音结束，{len(wav)} 字节")
            self._record_future = None

    def start(self) -> None:
        """启动监听（非阻塞）。重复调用不会叠加 listener。"""
        with self._lock:
            if self._listener is not None:
                return
            kb = _require_keyboard()
            self._listener = kb.Listener(
                on_press=self.on_press, on_release=self.on_release
            )
            self._listener.start()

    def stop(self) -> None:
        listener = None
        with self._lock:
            listener, self._listener = self._listener, None
            self._pressed_modifiers.clear()
            self._active_holds.clear()
            self._hold_by_primary.clear()
        if listener is not None:
            try:
                listener.stop()
            except Exception:  # noqa: BLE001
                pass
        if self.audio_recorder is not None:
            try:
                self.audio_recorder.stop_recording()
            except Exception:  # noqa: BLE001
                pass
        self._executor.shutdown(wait=False, cancel_futures=True)
        try:
            self.registry.unsubscribe(self.reload)
        except Exception:  # noqa: BLE001
            pass
