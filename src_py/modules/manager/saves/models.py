"""存档槽数据模型（重构版）。

修复对应清单：A1–A16

设计要点
────────
**存档是索引，不是数据仓库。**

    index.yaml          所有槽的元数据（列表展示用）
    <id>/data.yaml      该槽的路径指针 + UI 数据

真正的数据（角色消息、会话、记忆库）由**各管理器自己读写**，
存档只在 load 时把路径交给它们、在 save 时把它们交回的路径记下来。

上一版的错误：把消息正文、角色对象、配置快照塞进 section，
等于同一份数据两处存储 —— 双写、不一致、存档巨大。

**为什么用 YAML**：`index.yaml` / `data.yaml` 给人看，
且与技能系统统一（已有 read_yaml）。
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Any, Dict, List, Optional


def _now() -> datetime:
    return datetime.now()


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "")


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    s = str(value or "").strip()
    if not s:
        return _now()
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return _now()


# ─────────────────────────────────────────────────────────────
# Section 名常量
# ─────────────────────────────────────────────────────────────

class Section:
    MEMORY = "memory"
    CHARACTERS = "characters"
    CHAT_HISTORY = "chat_history"
    SERVER = "server"
    UI = "ui"

    @classmethod
    def all(cls) -> List[str]:
        return [cls.MEMORY, cls.CHARACTERS, cls.CHAT_HISTORY, cls.SERVER, cls.UI]

    #: A1：这些是"路径指针"段（data.yaml 里存的是路径，不是数据）
    PATH_SECTIONS = (MEMORY, CHARACTERS, CHAT_HISTORY)

    @classmethod
    def kind(cls, name: str) -> str:
        if name in cls.PATH_SECTIONS:
            return "path"
        if name == cls.UI:
            return "ui"        # A4：不写类型，前端决定
        return "content"       # server.config：完整存储


def default_section(name: str) -> Dict[str, Any]:
    """A3：各 section 的默认内容。"""
    if name == Section.MEMORY:
        return SaveSlotMemoryData().to_dict()
    if name == Section.CHARACTERS:
        return SaveSlotCharactersData().to_dict()
    if name == Section.CHAT_HISTORY:
        return SaveSlotChatHistoryData().to_dict()
    if name == Section.SERVER:
        return SaveSlotServerData().to_dict()
    return {}


# ─────────────────────────────────────────────────────────────
# A3：四段数据结构
# ─────────────────────────────────────────────────────────────

@dataclass
class SaveSlotMemoryData:
    """记忆数据（只记路径，记忆系统自己读）。"""

    path: str = ""
    is_db: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "is_db": bool(self.is_db)
        }

    @classmethod
    def from_dict(cls, data: Any) -> "SaveSlotMemoryData":
        d = data if isinstance(data, dict) else {}
        return cls(path=str(d.get("path") or ""), is_db=bool(d.get("is_db", False)))


@dataclass
class SaveSlotCharactersData:
    """角色数据。

    A14：角色消息按 character_id 分目录存
    `{path}/<character_id>/messages.pkl`，所以这里只存**目录**路径。
    """

    path: str = ""
    last_used_character_id: str = ""
    #: A15：最近 20 条，用于启动快速回滚，**不是**完整历史
    last_used_character_messages: str = ""
    last_used_character_session_id: str = ""

    #: A15：快速回滚保留条数
    QUICK_ROLLBACK_MESSAGES: int = 20

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "last_used_character_id": self.last_used_character_id,
            "last_used_character_messages": self.last_used_character_messages,
            "last_used_character_session_id": self.last_used_character_session_id,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "SaveSlotCharactersData":
        d = data if isinstance(data, dict) else {}
        return cls(
            path=str(d.get("path") or ""),
            last_used_character_id=str(d.get("last_used_character_id") or ""),
            last_used_character_messages=str(
                d.get("last_used_character_messages") or ""),
            last_used_character_session_id=str(
                d.get("last_used_character_session_id") or ""),
        )


@dataclass
class SaveSlotChatHistoryData:
    """聊天历史数据（只记路径 + 最近会话 id 列表）。"""

    path: str = ""
    recent_sessions: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path, 
            "recent_sessions": self.recent_sessions
        }

    @classmethod
    def from_dict(cls, data: Any) -> "SaveSlotChatHistoryData":
        d = data if isinstance(data, dict) else {}
        return cls(
            path=str(d.get("path") or ""),
            recent_sessions=str(d.get("recent_sessions") or ""),
        )


@dataclass
class SaveSlotServerData:
    """服务数据。appconfig **完整存储**，读档要能完整恢复服务配置。"""

    config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.config or {})

    @classmethod
    def from_dict(cls, data: Any) -> "SaveSlotServerData":
        d = data if isinstance(data, dict) else {}
        cfg = d.get("config")
        return cls(config=dict(cfg) if isinstance(cfg, dict) else {})


def section_from_dict(name: str, data: Any) -> Any:
    """按 section 名构造对应的数据类。"""
    if name == Section.MEMORY:
        return SaveSlotMemoryData.from_dict(data)
    if name == Section.CHARACTERS:
        return SaveSlotCharactersData.from_dict(data)
    if name == Section.CHAT_HISTORY:
        return SaveSlotChatHistoryData.from_dict(data)
    if name == Section.SERVER:
        return SaveSlotServerData.from_dict(data)
    if name == Section.UI:
        return data if isinstance(data, dict) else {}
    return data if isinstance(data, dict) else {}


# ─────────────────────────────────────────────────────────────
# 元数据（列表展示用）
# ─────────────────────────────────────────────────────────────

@dataclass
class SaveSlotMeta:
    """槽位元数据。index.yaml"""

    create_time: datetime = field(default_factory=_now)
    update_time: datetime = field(default_factory=_now)
    last_chat: str = ""
    description: str = ""
    #: A8：界面截图**完整路径**，没有则空串
    snapshot_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "create_time": _iso(self.create_time),
            "update_time": _iso(self.update_time),
            "last_chat": self.last_chat,
            "description": self.description,
            "snapshot_path": self.snapshot_path,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "SaveSlotMeta":
        d = data if isinstance(data, dict) else {}
        return cls(
            create_time=_parse_dt(d.get("create_time")),
            update_time=_parse_dt(d.get("update_time")),
            last_chat=str(d.get("last_chat") or ""),
            description=str(d.get("description") or ""),
            snapshot_path=str(d.get("snapshot_path") or ""),
        )


# ─────────────────────────────────────────────────────────────
# A5：槽位
# ─────────────────────────────────────────────────────────────

@dataclass
class SaveSlot:
    """一个存档槽。

    `loader` 表示 data.yaml 是否已读入内存。
    """

    id: str
    name: str
    meta: SaveSlotMeta = field(default_factory=SaveSlotMeta)
    #: 各 section 的路径等数据
    data: Dict[str, Any] = field(default_factory=dict)
    loader: bool = False

    # ---------- section ----------

    def get_section(self, name: str) -> Dict[str, Any]:
        """A5：已加载就直接返回；未加载则构造默认值放进内存。"""
        if self.loader:
            return self.data.get(name) or {}
        data: Any = None
        if not isinstance(data, dict):
            data = dict(default_section(name))
        self.data[name] = data
        return data

    def set_section(self, name: str, value: Dict[str, Any]) -> None:
        self.data[name] = value
        self.touch()

    @property
    def memory(self) -> Dict[str, Any]:
        return self.get_section(Section.MEMORY)

    @memory.setter
    def memory(self, value: Dict[str, Any]) -> None:
        self.set_section(Section.MEMORY, value)

    @property
    def characters(self) -> Dict[str, Any]:
        return self.get_section(Section.CHARACTERS)

    @characters.setter
    def characters(self, value: Dict[str, Any]) -> None:
        self.set_section(Section.CHARACTERS, value)

    @property
    def chat_history(self) -> Dict[str, Any]:
        return self.get_section(Section.CHAT_HISTORY)

    @chat_history.setter
    def chat_history(self, value: Dict[str, Any]) -> None:
        self.set_section(Section.CHAT_HISTORY, value)

    @property
    def achievements(self) -> Dict[str, Any]:
        return self.get_section("achievements")

    @achievements.setter
    def achievements(self, value: Dict[str, Any]) -> None:
        self.set_section("achievements", value)

    @property
    def story(self) -> Dict[str, Any]:
        return self.get_section("story")

    @story.setter
    def story(self, value: Dict[str, Any]) -> None:
        self.set_section("story", value)

    # ---------- 序列化 ----------

    def touch(self) -> None:
        """A9：任何写入都刷新 update_time。"""
        self.meta.update_time = _now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "meta": self.meta.to_dict(),
            "data": dict(self.data)
        }

    @classmethod
    def from_dict(cls, data: Any) -> "SaveSlot":
        d = data if isinstance(data, dict) else {}
        return cls(
            id=str(d.get("id") or ""),
            name=str(d.get("name") or d.get("id") or ""),
            meta=SaveSlotMeta.from_dict(d.get("meta")),
            data=dict(d.get("data") or {}),
            loader=False
        )


__all__ = [
    "Section",
    "SaveSlotMeta",
    "SaveSlot",
    "SaveSlotMemoryData",
    "SaveSlotCharactersData",
    "SaveSlotChatHistoryData",
    "SaveSlotServerData",
    "default_section",
    "section_from_dict",
]
