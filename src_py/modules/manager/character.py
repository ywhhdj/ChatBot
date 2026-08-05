"""
character_system/manager.py — 角色管理器（全局单例）

核心职责:
    1. 角色的注册/注销/切换
    2. 每个角色独立的状态保存与恢复
    3. 全局共享一个"角色上下文"，切换 = 切回之前的状态
"""
from __future__ import annotations
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from src_py.modules.runtime import RuntimePath

from .task.decorator import sync_task_scheduler
from ..events import on_event_class,types
from ..utils.file import read_json, read_yaml, write_json
from ..logger import logger
from ..characters.models import (
    Character,
    CharacterState,
    CharacterAttributes,
    CharacterStatus
)

from .base import _BaseManager

@on_event_class([
    (types.AppEventType.ManagerEventType.CHARACTER_STOP, "stop")
])
class CharacterManager(_BaseManager):
    """
    全局角色管理器（单例）。

    设计要点:
        - 所有角色存储在 _characters 字典中
        - 当前活跃角色 _current_id，切换时自动保存旧角色状态
        - 持久化到 JSON 文件（可选）
        - 线程安全（使用锁）
    """

    def __init__(self, storage_path: str = "", auto_save: bool = False):
        if self._initialized:
            return
        self._characters: Dict[str, Character] = {}
        self._current_id: str = ""
        self._storage_path = storage_path
        self._auto_save = auto_save
        self._initialized = True

        # 加载持久化数据
        if storage_path and os.path.exists(storage_path):
            self.load()

    # ── 基础 CRUD ──────────────────────────────

    def register(self, character: Character) -> str:
        """注册新角色，返回角色 ID"""
        char_id = character.id or character.name
        self._characters[char_id] = character
        character.id = char_id
        character.updated_at = time.time()
        if self._auto_save:
            self.save()
        return char_id

    def unregister(self, char_id: str) -> bool:
        """注销角色"""
        if char_id in self._characters:
            del self._characters[char_id]
            if self._current_id == char_id:
                self._current_id = ""
            if self._auto_save:
                self.save()
            return True
        return False

    def get(self, char_id: str) -> Optional[Character]:
        return self._characters.get(char_id)

    def get_all(self) -> Dict[str, Character]:
        return dict(self._characters)

    def get_list(self) -> List[Dict[str, Any]]:
        """返回角色摘要列表（不含完整消息历史）"""
        result = []
        for cid, char in self._characters.items():
            result.append({
                "id": cid,
                "name": char.name,
                "title": char.attributes.title,
                "status": char.state.status.value,
                "mood": char.state.mood,
                "affection": char.state.affection,
                "total_messages": char.state.total_messages,
                "is_current": (cid == self._current_id),
            })
        return result

    # ── 切换 ──────────────────────────────

    def switch_to(self, char_id: str) -> bool:
        """切换到指定角色，自动保存当前角色状态"""
        if char_id not in self._characters:
            return False

        # 保存旧角色
        old_id = self._current_id
        if old_id and old_id in self._characters:
            self._characters[old_id].state.touch()
            self._characters[old_id].updated_at = time.time()

        # 切换
        self._current_id = char_id
        self._characters[char_id].state.status = CharacterStatus.ACTIVE
        self._characters[char_id].state.touch()

        # 旧角色标记为 idle
        if old_id and old_id != char_id and old_id in self._characters:
            self._characters[old_id].state.status = CharacterStatus.IDLE

        if self._auto_save:
            self.save()
        return True

    def get_current(self) -> Optional[Character]:
        """获取当前活跃角色"""
        if not self._current_id:
            return None
        return self._characters.get(self._current_id)

    @property
    def current_id(self) -> str:
        return self._current_id

    # ── 状态更新 ──────────────────────────────

    def update_mood(self, char_id: str, mood: str):
        """更新角色心情"""
        char = self._characters.get(char_id)
        if char:
            char.state.mood = mood
            char.attributes.mood = mood
            char.state.touch()

    def update_affection(self, char_id: str, delta: int):
        """增减好感度"""
        char = self._characters.get(char_id)
        if char:
            char.state.affection = max(0, min(100, char.state.affection + delta))
            char.attributes.affection_level = char.state.affection

    def add_message(self, char_id: str, role: str, content: str):
        """为指定角色添加一条消息"""
        char = self._characters.get(char_id)
        if char:
            char.state.add_message(role, content)

    def get_messages(self, char_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """获取角色最近 N 条消息"""
        char = self._characters.get(char_id)
        if not char:
            return []
        return char.state.messages[-limit:]

    def clear_messages(self, char_id: str):
        """清空角色消息历史"""
        char = self._characters.get(char_id)
        if char:
            char.state.messages = []

    # ── 任务管理 ──────────────────────────────

    def add_task(self, char_id: str, task: Dict[str, Any]):
        """为角色添加后台任务"""
        char = self._characters.get(char_id)
        if char:
            char.state.pending_tasks.append(task)
            char.state.touch()

    def get_pending_tasks(self, char_id: str) -> List[Dict[str, Any]]:
        return self._characters.get(char_id, Character()).state.pending_tasks

    def complete_task(self, char_id: str, task: Dict[str, Any], result: Dict[str, Any]):
        """完成任务，移入历史"""
        char = self._characters.get(char_id)
        if not char:
            return
        if task in char.state.pending_tasks:
            char.state.pending_tasks.remove(task)
        char.state.task_history.append({
            **task,
            "result": result,
            "completed_at": time.time(),
        })
        char.state.total_tasks += 1

    # ── 持久化 ──────────────────────────────

    @sync_task_scheduler
    def save(self):
        """保存到 JSON 文件"""
        if not self._storage_path:
            return
        os.makedirs(os.path.dirname(self._storage_path) or ".", exist_ok=True)
        data = {
            "id": self._current_id,
            "characters": {}
        }
        for cid, char in self._characters.items():
            data["characters"][cid] = {
                "id": char.id,
                "name": char.name,
                "attributes": {
                    "name": char.attributes.name,
                    "title": char.attributes.title,
                    "nickname_for_user": char.attributes.nickname_for_user,
                    "personality": char.attributes.personality,
                    "background": char.attributes.background,
                    "speech_style": char.attributes.speech_style,
                    "catchphrases": char.attributes.catchphrases,
                    "rules": char.attributes.rules,
                    "topics_allowed": char.attributes.topics_allowed,
                    "topics_forbidden": char.attributes.topics_forbidden,
                    "affection_level": char.attributes.affection_level,
                    "mood": char.attributes.mood,
                    "mood_modifiers": char.attributes.mood_modifiers,
                    "random_words": char.attributes.random_words,
                    "action_verbs": char.attributes.action_verbs,
                    "emotion_adjectives": char.attributes.emotion_adjectives,
                },
                "state": {
                    "character_id": char.state.character_id,
                    "status": char.state.status.value,
                    "messages": char.state.messages,
                    "max_memory": char.state.max_memory,
                    "mood": char.state.mood,
                    "affection": char.state.affection,
                    "last_interaction": char.state.last_interaction,
                    "pending_tasks": char.state.pending_tasks,
                    "task_history": char.state.task_history,
                    "total_messages": char.state.total_messages,
                    "total_tasks": char.state.total_tasks,
                },
                "created_at": char.created_at,
                "updated_at": char.updated_at,
            }
        try:
            write_json(self._storage_path, data)
        except Exception as e:
            logger.error(f"[CharacterManager] 保存失败: {e}")

    def load(self):
        """从 JSON 文件加载"""
        if not self._storage_path or not os.path.exists(self._storage_path):
            return
        try:
            data=read_json(self._storage_path)
            self._current_id = data.get("id", "")
            for cid, cdata in data.get("characters", {}).items():
                attr_data = cdata.get("attributes", {})
                state_data = cdata.get("state", {})
                char = Character(
                    id=cdata.get("id", cid),
                    name=cdata.get("name", ""),
                    attributes=CharacterAttributes(**attr_data),
                    state=CharacterState(
                        character_id=state_data.get("character_id", cid),
                        status=CharacterStatus(state_data.get("status", "idle")),
                        messages=state_data.get("messages", []),
                        max_memory=state_data.get("max_memory", 20),
                        mood=state_data.get("mood", "neutral"),
                        affection=state_data.get("affection", 50),
                        last_interaction=state_data.get("last_interaction", 0),
                        pending_tasks=state_data.get("pending_tasks", []),
                        task_history=state_data.get("task_history", []),
                        total_messages=state_data.get("total_messages", 0),
                        total_tasks=state_data.get("total_tasks", 0),
                    ),
                    created_at=cdata.get("created_at", time.time()),
                    updated_at=cdata.get("updated_at", time.time()),
                )
                self._characters[cid] = char
        except Exception as e:
            logger.error(f"[CharacterManager] 加载失败: {e}")

    def set_storage_path(self, path: str):
        self._storage_path = path

    def set_auto_save(self, enabled: bool):
        self._auto_save = enabled
    
    def stop(self):
        self.save()
        self._characters.clear()
    
    @sync_task_scheduler
    def load_default_characters(self):
        path= RuntimePath.get_roles_file_path()
        for file in Path(path).glob("*.yaml"):
            data = read_yaml(file)
            self.register(Character(**data))

character_manager = CharacterManager()
# character_manager.load_default_characters()