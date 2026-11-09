"""快捷键映射与热键绑定注册表（后端权威）。

职责边界
────────
* 后端（本模块 + controllers/hotkeys.py）：动作白名单、组合键规范化、
  合法性/保留键/冲突校验、持久化到用户数据目录、revision 乐观并发、
  变更后通知键盘设备重载。
* 前端：热键**录制交互**（捕获 KeyboardEvent）、设置页 UI、展示。
  键位字符串契约与录制流程见 `docs/HotkeyFrontendContract.md`。

键位字符串统一形如 ``Ctrl+Shift+A``：修饰键固定顺序 Ctrl/Alt/Shift/Meta，
主键大写；前端传 ``ctrl+shift+keya`` 之类的别名也能被规范化。
"""

from __future__ import annotations

import json
import os
import sys
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..logger import logger
from ..runtime import StandardPaths
from ..utils.file.atomic import atomic_write_json

BINDING_SCHEMA_VERSION = 1

#: 修饰键输出顺序（也是组合键规范化后的顺序）
MODIFIER_ORDER: Tuple[str, ...] = ("Ctrl", "Alt", "Shift", "Meta")

MODIFIER_ALIASES: Dict[str, str] = {
    "ctrl": "Ctrl", "control": "Ctrl", "ctl": "Ctrl",
    "alt": "Alt", "option": "Alt", "opt": "Alt",
    "shift": "Shift",
    "meta": "Meta", "cmd": "Meta", "command": "Meta", "super": "Meta",
    "win": "Meta", "windows": "Meta",
}

KEY_ALIASES: Dict[str, str] = {
    "esc": "Esc", "escape": "Esc",
    "enter": "Enter", "return": "Enter",
    "space": "Space", "spacebar": "Space", " ": "Space",
    "backspace": "Backspace", "tab": "Tab",
    "delete": "Delete", "del": "Delete", "insert": "Insert",
    "home": "Home", "end": "End",
    "pageup": "PageUp", "pagedown": "PageDown",
    "capslock": "CapsLock", "caps_lock": "CapsLock",
    "up": "Up", "arrowup": "Up", "down": "Down", "arrowdown": "Down",
    "left": "Left", "arrowleft": "Left", "right": "Right", "arrowright": "Right",
    "printscreen": "PrintScreen", "scrolllock": "ScrollLock", "pause": "Pause",
}

#: 允许的主键字符（字母数字、功能键、常见标点）
_SIMPLE_KEY_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789-=[]\\;',./`")

#: 系统/窗口/编辑器基础组合，禁止被应用全局热键占用
RESERVED_COMBOS = frozenset({
    "Ctrl+Alt+Delete", "Ctrl+Shift+Esc", "Alt+F4", "Alt+Tab",
    "Meta+Q", "Meta+Space", "Meta+Tab", "Ctrl+Alt+F12",
    "Ctrl+C", "Ctrl+V", "Ctrl+X", "Ctrl+A", "Ctrl+Z", "Ctrl+Y",
    "Meta+C", "Meta+V", "Meta+X", "Meta+A", "Meta+Z",
    "Ctrl+W", "Ctrl+T", "Ctrl+N", "Ctrl+P", "Ctrl+F",
    "Meta+W", "Meta+T", "Meta+N", "Meta+P", "Meta+F",
})

#: 动作白名单。新增动作必须在这里登记，前端只能改这里声明过的动作。
DEFAULT_ACTIONS: Tuple[Dict[str, Any], ...] = (
    {"id": "record", "label": "按住录音", "group": "input", "mode": "hold",
     "binding": "Ctrl+Space", "description": "按住开始录音，松开结束并发送"},
    {"id": "interrupt", "label": "打断当前回复", "group": "chat", "mode": "press",
     "binding": "Esc", "description": "中断当前生成 / 播放"},
    {"id": "send_message", "label": "发送消息", "group": "input", "mode": "press",
     "binding": "Ctrl+Enter", "description": "在输入框内提交当前内容"},
    {"id": "new_session", "label": "新建会话", "group": "session", "mode": "press",
     "binding": "Ctrl+Shift+N", "description": "创建并切换到新会话"},
    {"id": "switch_session", "label": "切换会话", "group": "session", "mode": "press",
     "binding": "Ctrl+Shift+Tab", "description": "在最近两个会话间切换"},
    {"id": "flush_session", "label": "会话落盘", "group": "session", "mode": "press",
     "binding": "Ctrl+Shift+S", "description": "立即把会话消息写入磁盘"},
    {"id": "quick_save", "label": "快速存档", "group": "save", "mode": "press",
     "binding": "Ctrl+S", "description": "保存到当前存档槽"},
    {"id": "quick_load", "label": "快速读档", "group": "save", "mode": "press",
     "binding": "Ctrl+L", "description": "加载当前存档槽"},
    {"id": "restore_sessions", "label": "从存档恢复会话", "group": "save", "mode": "press",
     "binding": "Ctrl+Shift+R", "description": "把当前槽的会话恢复到会话管理器"},
    {"id": "open_settings", "label": "打开设置", "group": "app", "mode": "press",
     "binding": "Ctrl+,", "description": "打开设置页"},
    {"id": "toggle_window", "label": "显示/隐藏主窗口", "group": "app", "mode": "press",
     "binding": "Ctrl+Shift+H", "description": "最小化或唤起主窗口"},
)

ACTION_IDS = frozenset(a["id"] for a in DEFAULT_ACTIONS)
ACTION_BY_ID: Dict[str, Dict[str, Any]] = {a["id"]: a for a in DEFAULT_ACTIONS}
DEFAULT_BINDINGS: Dict[str, str] = {a["id"]: a["binding"] for a in DEFAULT_ACTIONS}


class HotkeyError(ValueError):
    """带稳定原因码的校验错误，便于前端按 code 出提示。"""

    def __init__(self, code: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra


def platform_key() -> str:
    if sys.platform.startswith("darwin"):
        return "macos"
    if sys.platform.startswith("win"):
        return "windows"
    return "linux"


def _normalize_key(token: str) -> str:
    """把单个 token 规范成主键；返回空串表示它是修饰键。"""
    low = token.strip().lower()
    if low in MODIFIER_ALIASES:
        return ""
    if low in KEY_ALIASES:
        return KEY_ALIASES[low]
    # KeyboardEvent.code 形态：KeyA / Digit1 / F5 / Numpad1
    if low.startswith("key") and len(low) == 4 and low[3].isalpha():
        return low[3].upper()
    if low.startswith("digit") and len(low) == 6 and low[5].isdigit():
        return low[5]
    if low.startswith("f") and low[1:].isdigit() and 1 <= int(low[1:]) <= 12:
        return "F" + low[1:]
    if len(low) == 1 and low in _SIMPLE_KEY_CHARS:
        return low.upper() if low.isalpha() else low
    return ""


def normalize_combo(raw: str) -> str:
    """规范化组合键；不合法抛 HotkeyError('invalid_format'|'modifier_only')。

    ``Ctrl+Shift+A`` → ``Ctrl+Shift+A``
    ``cmd + shift + keya`` → ``Meta+Shift+A``
    """
    if not isinstance(raw, str) or not raw.strip():
        raise HotkeyError("invalid_format", "组合键不能为空")
    text = raw.strip()
    if len(text) > 64:
        raise HotkeyError("invalid_format", "组合键过长（上限 64 字符）")
    parts = [p.strip() for p in text.split("+")]
    if any(not p for p in parts):
        raise HotkeyError("invalid_format", "组合键格式错误：存在空片段")

    modifiers: List[str] = []
    primary = ""
    for part in parts:
        low = part.lower()
        if low in MODIFIER_ALIASES:
            mod = MODIFIER_ALIASES[low]
            if mod in modifiers:
                raise HotkeyError("invalid_format", f"修饰键重复: {mod}")
            modifiers.append(mod)
            continue
        key = _normalize_key(part)
        if not key:
            raise HotkeyError("invalid_format", f"无法识别的按键: {part!r}")
        if primary:
            raise HotkeyError("invalid_format", "组合键只能有一个主键")
        primary = key
    if not primary:
        raise HotkeyError("modifier_only", "只有修饰键不能作为热键，请补一个主键")
    ordered = [m for m in MODIFIER_ORDER if m in modifiers]
    return "+".join(ordered + [primary])


def display_combo(combo: str, platform: str = "") -> str:
    """按平台给前端展示；macOS 用 ⌘⌥⇧⌃，其它平台保留完整单词。"""
    pf = platform or platform_key()
    parts = combo.split("+") if combo else []
    if pf != "macos":
        return combo
    symbols = {"Ctrl": "⌃", "Alt": "⌥", "Shift": "⇧", "Meta": "⌘"}
    head = [symbols.get(p, p) for p in parts[:-1]]
    return "".join(head + parts[-1:])


def _config_path() -> str:
    return os.path.join(str(StandardPaths.get_user_data_dir()), "config", "hotkeys.json")


class HotkeyRegistry:
    """线程安全的绑定注册表。所有写操作都是「先全量校验，再一次原子写」。"""

    _instance: Optional["HotkeyRegistry"] = None
    _cls_lock = threading.Lock()

    def __new__(cls, *args: Any, **kwargs: Any) -> "HotkeyRegistry":
        if cls._instance is None:
            with cls._cls_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config_path: Optional[str] = None) -> None:
        if getattr(self, "_initialized", False):
            return
        self._path = config_path or _config_path()
        self._lock = threading.RLock()
        self._bindings: Dict[str, str] = dict(DEFAULT_BINDINGS)
        self._revision = 0
        self._listeners: List[Callable[["HotkeyRegistry"], None]] = []
        self._initialized = True
        self._load()

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    # ---------- 持久化 ----------

    def _load(self) -> None:
        try:
            if not os.path.isfile(self._path):
                return
            with open(self._path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except Exception as exc:  # noqa: BLE001 - 坏配置不能让应用起不来
            logger.warning(f"[Hotkey] 配置读取失败，使用默认映射: {exc}")
            return
        if not isinstance(raw, dict) or raw.get("version") != BINDING_SCHEMA_VERSION:
            logger.warning("[Hotkey] 配置版本不匹配，使用默认映射")
            return
        stored = raw.get("bindings")
        if not isinstance(stored, dict):
            return
        candidate: Dict[str, str] = {}
        for action, combo in stored.items():
            if action not in ACTION_IDS or not isinstance(combo, str):
                continue
            try:
                normalized = normalize_combo(combo)
                self._check_reserved(normalized)
            except HotkeyError as exc:
                logger.warning(f"[Hotkey] 忽略非法绑定 {action}={combo!r}: {exc.message}")
                continue
            candidate[action] = normalized
        # 用户可能手工编辑出重复组合：按动作声明顺序保留先出现的，后者回落默认。
        # 必须遍历 DEFAULT_ACTIONS 而不是 frozenset（顺序不固定会让回落结果随机）。
        taken: Dict[str, str] = {}
        resolved: Dict[str, str] = {}
        for spec in DEFAULT_ACTIONS:
            action = spec["id"]
            value = candidate.get(action, DEFAULT_BINDINGS[action])
            owner = taken.get(value)
            if owner:
                fallback = DEFAULT_BINDINGS[action]
                if fallback in taken:
                    logger.warning(f"[Hotkey] {action} 无可用组合，已禁用")
                    value = ""
                else:
                    logger.warning(f"[Hotkey] {action} 与 {owner} 冲突，回落到 {fallback}")
                    value = fallback
            if value:
                taken[value] = action
            resolved[action] = value
        self._bindings = resolved
        try:
            self._revision = int(raw.get("revision") or 0)
        except (TypeError, ValueError):
            self._revision = 0

    def _persist(self) -> None:
        atomic_write_json(self._path, {
            "version": BINDING_SCHEMA_VERSION,
            "revision": self._revision,
            "bindings": dict(self._bindings),
        })

    # ---------- 校验 ----------

    @staticmethod
    def _check_reserved(combo: str) -> None:
        if combo in RESERVED_COMBOS:
            raise HotkeyError(
                "reserved", f"{combo} 是系统/编辑器保留组合，不能绑定",
                combo=combo,
            )

    def _conflict_with(self, combo: str, exclude_action: str = "") -> str:
        for action, bound in self._bindings.items():
            if action != exclude_action and bound == combo:
                return action
        return ""

    def validate(
        self,
        combo: str,
        exclude_action: str = "",
        *,
        check_conflict: bool = True,
    ) -> Dict[str, Any]:
        """纯校验，不抛异常 —— 供前端录制时实时调用。"""
        try:
            normalized = normalize_combo(combo)
            self._check_reserved(normalized)
        except HotkeyError as exc:
            return {
                "valid": False, "code": exc.code, "reason": exc.message,
                "normalized": "", "display": "", "conflict_with": "",
            }
        conflict = self._conflict_with(normalized, exclude_action) if check_conflict else ""
        if conflict:
            return {
                "valid": False, "code": "conflict",
                "reason": f"该组合已被「{ACTION_BY_ID[conflict]['label']}」占用",
                "normalized": normalized,
                "display": display_combo(normalized),
                "conflict_with": conflict,
            }
        return {
            "valid": True, "code": "", "reason": "",
            "normalized": normalized, "display": display_combo(normalized),
            "conflict_with": "",
        }

    def _check_revision(self, revision: Optional[int]) -> None:
        if revision is None:
            return
        try:
            expected = int(revision)
        except (TypeError, ValueError) as exc:
            raise HotkeyError("stale_revision", "revision 必须是整数") from exc
        if expected != self._revision:
            raise HotkeyError(
                "stale_revision",
                f"配置已被其他端修改（服务端 revision={self._revision}），请刷新后重试",
                server_revision=self._revision,
            )

    # ---------- 查询 ----------

    def bindings(self) -> Dict[str, str]:
        with self._lock:
            return dict(self._bindings)

    def describe(self) -> Dict[str, Any]:
        with self._lock:
            pf = platform_key()
            actions = []
            for spec in DEFAULT_ACTIONS:
                action = spec["id"]
                combo = self._bindings.get(action, "")
                actions.append({
                    "id": action,
                    "label": spec["label"],
                    "description": spec["description"],
                    "group": spec["group"],
                    "mode": spec["mode"],
                    "editable": True,
                    "binding": combo,
                    "display": display_combo(combo, pf) if combo else "",
                    "is_default": combo == spec["binding"],
                    "default": spec["binding"],
                })
            return {
                "version": BINDING_SCHEMA_VERSION,
                "revision": self._revision,
                "platform": pf,
                "key_format": "Ctrl+Shift+A（修饰键顺序 Ctrl/Alt/Shift/Meta）",
                "actions": actions,
                "reserved": sorted(RESERVED_COMBOS),
                "config_path": self._path,
            }

    # ---------- 修改 ----------

    def set_binding(
        self,
        action: str,
        combo: str,
        revision: Optional[int] = None,
    ) -> Dict[str, Any]:
        """接受前端修改单个热键。返回 (describe, normalized)。"""
        with self._lock:
            self._check_revision(revision)
            if action not in ACTION_IDS:
                raise HotkeyError("unknown_action", f"未知动作: {action}")
            normalized = normalize_combo(combo)
            self._check_reserved(normalized)
            conflict = self._conflict_with(normalized, action)
            if conflict:
                raise HotkeyError(
                    "conflict",
                    f"{normalized} 已被「{ACTION_BY_ID[conflict]['label']}」占用",
                    conflict_with=conflict,
                )
            new_bindings = dict(self._bindings)
            new_bindings[action] = normalized
            old_bindings, old_revision = dict(self._bindings), self._revision
            self._bindings = new_bindings
            self._revision += 1
            try:
                self._persist()
            except Exception as exc:  # noqa: BLE001
                self._bindings, self._revision = old_bindings, old_revision
                logger.error(f"[Hotkey] 持久化失败: {exc}")
                raise HotkeyError("persist_failed", f"热键保存失败: {exc}") from exc
            result = self.describe()
        self._notify()
        return {"registry": result, "normalized": normalized}

    def set_many(
        self,
        bindings: Dict[str, str],
        revision: Optional[int] = None,
    ) -> Dict[str, Any]:
        """批量修改：**全量校验通过才一次写盘**，避免部分成功。

        前端设置页「保存全部」用这个；`bindings` 只传要改的动作。
        """
        if not isinstance(bindings, dict) or not bindings:
            raise HotkeyError("invalid_format", "bindings 不能为空")
        with self._lock:
            self._check_revision(revision)
            unknown = [k for k in bindings if k not in ACTION_IDS]
            if unknown:
                raise HotkeyError("unknown_action", f"未知动作: {', '.join(unknown)}")
            candidate = dict(self._bindings)
            normalized_map: Dict[str, str] = {}
            for action, combo in bindings.items():
                normalized = normalize_combo(combo)
                self._check_reserved(normalized)
                normalized_map[action] = normalized
                candidate[action] = normalized
            # 全量冲突检测（含未改动项）
            seen: Dict[str, str] = {}
            for spec in DEFAULT_ACTIONS:
                action = spec["id"]
                combo = candidate.get(action, "")
                if not combo:
                    continue
                if combo in seen:
                    raise HotkeyError(
                        "conflict",
                        f"{combo} 同时绑定到「{ACTION_BY_ID[seen[combo]]['label']}」"
                        f"与「{spec['label']}」",
                        conflict_with=seen[combo],
                    )
                seen[combo] = action
            old_bindings, old_revision = dict(self._bindings), self._revision
            self._bindings = candidate
            self._revision += 1
            try:
                self._persist()
            except Exception as exc:  # noqa: BLE001
                self._bindings, self._revision = old_bindings, old_revision
                logger.error(f"[Hotkey] 批量持久化失败: {exc}")
                raise HotkeyError("persist_failed", f"热键保存失败: {exc}") from exc
            result = self.describe()
        self._notify()
        return {"registry": result, "normalized": normalized_map}

    def reset(self, revision: Optional[int] = None) -> Dict[str, Any]:
        with self._lock:
            self._check_revision(revision)
            old_bindings, old_revision = dict(self._bindings), self._revision
            self._bindings = dict(DEFAULT_BINDINGS)
            self._revision += 1
            try:
                self._persist()
            except Exception as exc:  # noqa: BLE001
                self._bindings, self._revision = old_bindings, old_revision
                logger.error(f"[Hotkey] 重置持久化失败: {exc}")
                raise HotkeyError("persist_failed", f"热键保存失败: {exc}") from exc
            result = self.describe()
        self._notify()
        return {"registry": result}

    # ---------- 变更通知（设备侧重载） ----------

    def subscribe(self, listener: Callable[["HotkeyRegistry"], None]) -> None:
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def unsubscribe(self, listener: Callable[["HotkeyRegistry"], None]) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def _notify(self) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for fn in listeners:
            try:
                fn(self)
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[Hotkey] 变更通知失败: {exc}")


def get_hotkey_registry() -> HotkeyRegistry:
    return HotkeyRegistry()
