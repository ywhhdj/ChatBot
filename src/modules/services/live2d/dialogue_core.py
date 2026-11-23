"""EnhancedDialogueComponent """
from __future__ import annotations

import html
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .behavior import PAUSE_PUNCTUATION
from .settings import normalize


@dataclass
class DialogueEvent:
    kind: str
    data: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"DialogueEvent({self.kind}, {self.data})"


@dataclass
class BacklogEntry:
    speaker: str
    text: str
    emotion: str = ""
    read: bool = False
    ts: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "speaker": self.speaker, "text": self.text,
            "emotion": self.emotion, "read": self.read, "ts": self.ts,
        }


@dataclass
class DialogueLine:
    text: str
    speaker: str = ""
    emotion: str = ""
    instant: bool = False
    choices: List[str] = field(default_factory=list)
    read: bool = False
    meta: Dict[str, Any] = field(default_factory=dict)


class DialogueEngine:
    """打字节奏与状态机。``tick(dt_ms)`` 由 QTimer 驱动，返回事件列表。

    状态：``idle → typing → waiting → (advance/auto) → idle``
    选项态 ``choice`` 会等 ``choose()``，不自动推进。
    """

    def __init__(self, cfg: Optional[Dict[str, Any]] = None,
                 clock: Optional[Any] = None):
        self.cfg = normalize(cfg)
        self._clock = clock or time.monotonic
        self.state = "idle"
        self.line: Optional[DialogueLine] = None
        self.displayed = ""
        self._index = 0
        self._acc_ms = 0.0
        self._pause_left_ms = 0.0
        self._auto_left_ms = 0.0
        self._queue: List[DialogueLine] = []
        self.backlog: List[BacklogEntry] = []
        self.read_keys: set[str] = set()
        self.choices: List[str] = []
        self._choice_index: Optional[int] = None
        self.enabled = True

    # ── 配置 ──────────────────────────────────────────────────────

    def update_config(self, cfg: Dict[str, Any]) -> None:
        self.cfg = normalize(cfg)
        self._acc_ms = 0.0

    @property
    def char_interval_ms(self) -> float:
        """单个字符的间隔（毫秒）；``batch_size`` 在 tick 里作为每步字数。"""
        return self._char_interval()

    def _char_interval(self) -> float:
        cps = max(1.0, float(self.cfg.get("dialogue_typing_cps", 30)))
        return max(1.0, 1000.0 / cps)

    # ── 推入台词 ──────────────────────────────────────────────────

    def show(
        self,
        text: str,
        speaker: str = "",
        emotion: str = "",
        instant: Optional[bool] = None,
        choices: Optional[Sequence[str]] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> List[DialogueEvent]:
        text = str(text or "")
        if not text and not choices:
            return []
        key = f"{speaker}\x00{text}"
        line = DialogueLine(
            text=text, speaker=str(speaker or ""), emotion=str(emotion or ""),
            instant=bool(self.cfg.get("dialogue_instant", False)) if instant is None else bool(instant),
            choices=list(choices or []), read=key in self.read_keys,
            meta=dict(meta or {}),
        )
        mode = str(self.cfg.get("dialogue_queue_mode", "interrupt"))
        events: List[DialogueEvent] = []
        if self.state in ("typing", "waiting", "choice") and mode == "queue":
            self._queue.append(line)
            events.append(DialogueEvent("queued", {
                "text": text, "queue_size": len(self._queue)}))
            return events

        # interrupt（galgame 默认）：新台词立刻顶掉当前，队列清空
        self._queue.clear()
        events.extend(self._begin(line))
        return events

    def _begin(self, line: DialogueLine) -> List[DialogueEvent]:
        self.line = line
        self.displayed = ""
        self._index = 0
        self._acc_ms = 0.0
        self._pause_left_ms = 0.0
        self._auto_left_ms = 0.0
        self.choices = list(line.choices)
        self._choice_index = None
        events = [
            DialogueEvent("line_started", {
                "speaker": line.speaker, "text": line.text,
                "emotion": line.emotion, "instant": line.instant,
                "choices": list(line.choices), "read": line.read,
            }),
        ]
        if self.cfg.get("dialogue_emotion_sync", True):
            events.append(DialogueEvent("speaking", {"on": True, "emotion": line.emotion}))
        self._append_backlog(line)
        if line.instant:
            self.displayed = line.text
            self._index = len(line.text)
            events.append(DialogueEvent("text_changed", {
                "text": self.displayed, "progress": 1.0}))
            events.extend(self._finish())
        else:
            self.state = "typing"
            events.append(DialogueEvent("typing_started", {"length": len(line.text)}))
        return events

    def _append_backlog(self, line: DialogueLine) -> None:
        limit = max(0, int(self.cfg.get("dialogue_backlog_size", 100)))
        if limit <= 0:
            return
        self.backlog.append(BacklogEntry(
            speaker=line.speaker, text=line.text, emotion=line.emotion,
            read=bool(line.read), ts=self._clock()))
        if len(self.backlog) > limit:
            del self.backlog[:len(self.backlog) - limit]

    # ── 帧驱动 ────────────────────────────────────────────────────

    def tick(self, dt_ms: float) -> List[DialogueEvent]:
        events: List[DialogueEvent] = []
        if not self.enabled or self.line is None:
            return events
        dt_ms = max(0.0, float(dt_ms))

        if self.state == "typing":
            if self._pause_left_ms > 0:
                used = min(self._pause_left_ms, dt_ms)
                self._pause_left_ms -= used
                dt_ms -= used
            self._acc_ms += dt_ms
            interval = self._char_interval()
            batch = max(1, int(self.cfg.get("dialogue_batch_size", 1)))
            guard = 0
            while self._acc_ms >= interval and self._index < len(self.line.text) and guard < 512:
                self._acc_ms -= interval
                guard += 1
                step = min(batch, len(self.line.text) - self._index)
                chunk = self.line.text[self._index:self._index + step]
                self._index += step
                self.displayed += chunk
                events.append(DialogueEvent("char_typed", {
                    "chunk": chunk, "index": self._index,
                    "sound": bool(self.cfg.get("dialogue_typewriter_sound", False)),
                }))
                # 标点停顿：只在刚打出的字符含标点时追加，且不吃掉后续 dt
                pause = float(self.cfg.get("dialogue_punctuation_pause_ms", 180))
                if pause > 0 and any(ch in PAUSE_PUNCTUATION for ch in chunk):
                    self._pause_left_ms += pause
                    # 停顿期间不累积时间，否则恢复后会一次性补打一串字
                    self._acc_ms = 0.0
                    break
            events.append(DialogueEvent("text_changed", {
                "text": self.displayed,
                "progress": (self._index / max(1, len(self.line.text))),
            }))
            if self._pause_left_ms > 0 and self._index < len(self.line.text):
                return events
            if self._index >= len(self.line.text):
                events.extend(self._finish())

        elif self.state == "waiting":
            auto_s = float(self.cfg.get("dialogue_auto_seconds", 0.0))
            if auto_s > 0 and not self.choices:
                self._auto_left_ms -= dt_ms
                if self._auto_left_ms <= 0:
                    events.append(DialogueEvent("auto_advance", {"line": self.line.text}))
                    self._auto_left_ms = auto_s * 1000.0
        return events

    def _finish(self) -> List[DialogueEvent]:
        assert self.line is not None
        key = f"{self.line.speaker}\x00{self.line.text}"
        self.read_keys.add(key)
        self.line.read = True
        if self.backlog and self.backlog[-1].text == self.line.text:
            self.backlog[-1].read = True
        self.state = "choice" if self.choices else "waiting"
        self._auto_left_ms = float(self.cfg.get("dialogue_auto_seconds", 0.0)) * 1000.0
        events = [
            DialogueEvent("typing_finished", {
                "text": self.line.text, "choices": list(self.choices)}),
            DialogueEvent("speaking", {"on": False, "emotion": ""}),
        ]
        if self.cfg.get("dialogue_indicator_visible", True) and not self.choices:
            events.append(DialogueEvent("indicator", {"visible": True}))
        return events

    # ── 交互 ──────────────────────────────────────────────────────

    def click(self, ctrl: bool = False) -> List[DialogueEvent]:
        """点击：打字中→立即显示完；等待中→推进下一段；选项态→忽略。"""
        if not self.cfg.get("dialogue_click_to_advance", True):
            return []
        if self.state == "choice":
            return []
        return self.advance(ctrl=ctrl)

    def skip(self) -> List[DialogueEvent]:
        return self.advance(skip=True)

    def advance(self, *, ctrl: bool = False, skip: bool = False) -> List[DialogueEvent]:
        events: List[DialogueEvent] = []
        if self.state == "typing" and self.line is not None:
            # Ctrl + 已读 / skip → 直接全显；普通点击也全显（galgame 惯例）
            fast = skip or (ctrl and self.cfg.get("dialogue_skip_read", True)
                            and self.line.read)
            self.displayed = self.line.text
            self._index = len(self.line.text)
            self._pause_left_ms = 0.0
            self._acc_ms = 0.0
            events.append(DialogueEvent("text_changed", {
                "text": self.displayed, "progress": 1.0, "skipped": fast}))
            events.extend(self._finish())
            return events
        if self.state in ("waiting", "choice"):
            events.append(DialogueEvent("indicator", {"visible": False}))
            if self._queue:
                events.extend(self._begin(self._queue.pop(0)))
            else:
                events.append(DialogueEvent("line_completed", {
                    "text": self.line.text if self.line else ""}))
                self.state = "idle"
                self.line = None
                self.displayed = ""
                self.choices = []
                events.append(DialogueEvent("speaking", {"on": False, "emotion": ""}))
        return events

    def choose(self, index: int) -> List[DialogueEvent]:
        if self.state != "choice" or not (0 <= index < len(self.choices)):
            return []
        self._choice_index = index
        return [
            DialogueEvent("choice_selected", {
                "index": index, "value": self.choices[index]}),
            *self.advance(),
        ]

    def clear(self) -> List[DialogueEvent]:
        self._queue.clear()
        self.state = "idle"
        self.line = None
        self.displayed = ""
        self._index = 0
        self._acc_ms = 0.0
        self._pause_left_ms = 0.0
        self.choices = []
        self._choice_index = None
        return [
            DialogueEvent("cleared", {}),
            DialogueEvent("speaking", {"on": False, "emotion": ""}),
        ]

    def set_choices(self, choices: Sequence[str]) -> List[DialogueEvent]:
        self.choices = list(choices)
        if self.choices and self.state == "waiting":
            self.state = "choice"
            return [DialogueEvent("choices_shown", {"choices": list(self.choices)})]
        return []

    # ── 查询 ──────────────────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "state": self.state,
            "displayed": self.displayed,
            "full_text": self.line.text if self.line else "",
            "speaker": self.line.speaker if self.line else "",
            "emotion": self.line.emotion if self.line else "",
            "progress": (self._index / max(1, len(self.line.text))) if self.line else 0.0,
            "choices": list(self.choices),
            "choice_index": self._choice_index,
            "queue_size": len(self._queue),
            "backlog_size": len(self.backlog),
            "read_count": len(self.read_keys),
            "typing_cps": self.cfg.get("dialogue_typing_cps", 30),
            "punctuation_pause_ms": self.cfg.get("dialogue_punctuation_pause_ms", 180),
        }

    def backlog_page(self, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        rows = list(reversed(self.backlog))
        return [r.to_dict() for r in rows[offset:offset + max(1, limit)]]


# ─────────────────────────────────────────────────────────────────────────────
# 富文本与样式
# ─────────────────────────────────────────────────────────────────────────────

def to_rich_text(cfg: Dict[str, Any], raw: str, *, name: str = "") -> str:
    """把台词转成安全的 QLabel rich text。

    支持 ``<b>`` ``<i>`` ``<color=#RRGGBB>`` 三个内标记，其余一律转义，
    避免把模型输出 / 用户输入当 HTML 注入。描边与阴影用 CSS text-shadow。
    """
    c = normalize(cfg)
    text = html.escape(str(raw or ""), quote=False)
    text = text.replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")
    text = text.replace("&lt;i&gt;", "<i>").replace("&lt;/i&gt;", "</i>")
    import re
    text = re.sub(r"&lt;color=(#[0-9a-fA-F]{6})&gt;", r"<font color='\1'>", text)
    text = text.replace("&lt;/color&gt;", "</font>")
    text = text.replace("\n", "<br/>")
    css = []
    color = str(c.get("dialogue_text_color") or "#F5F0E6")
    css.append(f"color:{color}")
    if c.get("dialogue_shadow", True):
        css.append("text-shadow: 1px 1px 2px rgba(0,0,0,0.85)")
    if c.get("dialogue_outline", True):
        outline = str(c.get("dialogue_outline_color") or "#1A1420")
        css.append(f"-qt-text-outline: 1px {outline}")
    return f"<div style=\"{';'.join(css)}\">{text}</div>"


def parse_color(value: Any, fallback: str = "#0B0B14") -> tuple[int, int, int]:
    """``#RGB`` / ``#RRGGBB`` / ``rgb(r,g,b)`` → (r,g,b)。

    原实现对 ``#ABC`` 会 ``int('C',16)`` 抛异常，且不校验范围。
    """
    import re
    text = str(value or "").strip()
    if text.startswith("#"):
        hexpart = text[1:]
        if len(hexpart) == 3:
            hexpart = "".join(ch * 2 for ch in hexpart)
        if len(hexpart) == 6 and re.fullmatch(r"[0-9a-fA-F]{6}", hexpart):
            return (int(hexpart[0:2], 16), int(hexpart[2:4], 16), int(hexpart[4:6], 16))
    m = re.fullmatch(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", text, re.I)
    if m:
        return tuple(max(0, min(255, int(m.group(i)))) for i in (1, 2, 3))  # type: ignore
    fb = parse_color(fallback, "#000000") if fallback.startswith("#") else (0, 0, 0)
    return fb


def build_stylesheet(cfg: Dict[str, Any]) -> str:
    """一次性生成完整 QSS —— 修掉原来 `set_text_color` / `set_background_color`
    互相覆盖整份 stylesheet 的问题。"""
    c = normalize(cfg)
    r, g, b = parse_color(c.get("dialogue_bg_color"))
    opacity = max(0.0, min(1.0, float(c.get("dialogue_bg_opacity", 0.82))))
    radius = max(0, int(c.get("dialogue_border_radius", 14)))
    border_w = max(0, int(c.get("dialogue_border_width", 1)))
    border = parse_color(c.get("dialogue_border_color"), "#D9C7A7")
    padding = max(0, int(c.get("dialogue_padding", 18)))
    font = str(c.get("dialogue_font_family") or "Microsoft YaHei").replace('"', "")
    size = max(8, int(c.get("dialogue_font_size", 17)))
    name_size = max(8, int(c.get("dialogue_name_font_size", 15)))
    text_color = str(c.get("dialogue_text_color") or "#F5F0E6")
    name_color = str(c.get("dialogue_name_color") or "#FFD9A0")
    align = str(c.get("dialogue_text_align") or "left")
    align_flag = {"left": "left", "center": "center", "right": "right"}.get(align, "left")
    spacing = max(1.0, float(c.get("dialogue_line_spacing", 1.55)))

    return f"""
QWidget#dialogue_component {{
    background-color: rgba({r}, {g}, {b}, {opacity * 255:.0f});
    border: {border_w}px solid rgba({border[0]}, {border[1]}, {border[2]}, 210);
    border-radius: {radius}px;
}}
QWidget#dialogue_header {{
    background-color: rgba(0, 0, 0, 0.28);
    border-top-left-radius: {radius}px;
    border-top-right-radius: {radius}px;
}}
QLabel#dialogue_title {{
    color: {name_color};
    font-size: {name_size}px;
    font-family: "{font}";
    padding-left: 10px;
    background: transparent;
}}
QLabel#text_label {{
    color: {text_color};
    font-size: {size}px;
    font-family: "{font}";
    line-height: {spacing:.2f};
    qproperty-alignment: 'Align{align_flag.capitalize()} | AlignVCenter';
    padding: {padding}px;
    background: transparent;
}}
QLabel#dialogue_indicator {{
    color: {name_color};
    font-size: {max(10, size - 2)}px;
    background: transparent;
}}
QPushButton#dialogue_button {{
    background-color: rgba(255, 255, 255, 0.20);
    border: none;
    border-radius: 8px;
    padding: 4px 10px;
    color: {text_color};
    font-size: 12px;
    font-family: "{font}";
}}
QPushButton#dialogue_button:hover {{
    border: 1px solid rgba(255, 255, 255, 0.32);
    background-color: rgba(255, 255, 255, 0.30);
}}
QPushButton#dialogue_button:pressed {{
    background-color: rgba(255, 255, 255, 0.45);
}}
QPushButton#choice_button {{
    background-color: rgba(255, 255, 255, 0.12);
    border: 1px solid rgba(255, 255, 255, 0.28);
    border-radius: 8px;
    padding: 6px 14px;
    color: {text_color};
    font-size: {size}px;
    font-family: "{font}";
    text-align: {align_flag};
}}
QPushButton#choice_button:hover {{
    background-color: rgba(255, 217, 160, 0.28);
    color: #FFFFFF;
}}
""".strip()


def validate_dialogue_config(cfg: Dict[str, Any]) -> List[str]:
    """返回人类可读的校验问题列表，供 /api/live2d/dialogue 与测试用。"""
    c = normalize(cfg)
    problems: List[str] = []
    w = int(c.get("dialogue_max_width", 1000))
    h = int(c.get("dialogue_height", 200))
    if w < 320:
        problems.append("dialogue_max_width 不能小于 320")
    if h < 100:
        problems.append("dialogue_height 不能小于 100")
    if c.get("dialogue_auto_seconds", 0) and c.get("dialogue_queue_mode") == "queue":
        problems.append("自动推进建议配合 queue 以外的模式，否则会连续弹出")
    if not math.isfinite(float(c.get("dialogue_typing_cps", 30))):
        problems.append("dialogue_typing_cps 必须是有限数")
    return problems
