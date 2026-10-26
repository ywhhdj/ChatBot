"""角色管理器（单例）。

这里按两处调用点反推出最小可用接口：

    character_manager.get_current() -> Optional[Character]
    character_manager.get(id)       -> Optional[Character]
    character_manager.switch(id)    -> bool
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, List, Literal, Optional

from src_py.modules import runtime

from ..characters.models import Character, CharacterAttributes, CharacterState
from ..logger import logger

DEFAULT_CHARACTER_ID = "qingmei"


class CharacterManager:
    """角色注册表 + 当前角色指针。"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._rwlock = threading.RLock()
        self._characters: Dict[str, Character] = {}
        self._current_id: Optional[str] = None
        self._save_path = ""
    
    def load_characters(self) -> None:
        """从存档加载角色。"""
        from ..characters.presets import load_character
        data = runtime.manager.save_manager.character

        self._save_path = data.get("path","")
        if self._save_path:
            characters = load_character(self._save_path)
            for char in characters:
                self._characters[str(char.id)] = char
            logger.info(f"[Character] 加载角色 {char.id} 成功")
        else:
            self._load_defaults()
            logger.warning(f"[Character] 加载角色失败，使用默认角色")
            #使用默认路径
            self._save_path = os.path.join(self._save_path, DEFAULT_CHARACTER_ID)


    # ---------- 初始化 ----------

    def _load_defaults(self) -> None:
        """预置默认角色，保证 `get_current()` 永远可用。"""
        candidates: List[Any] = []
        try:
            from ..characters.presets import create_defaults
            produced = create_defaults()
            candidates.extend(produced)
        except Exception as e:
            logger.warning(f"[Character] 默认角色创建失败: {e}")

        if not candidates:
            try:
                from ..characters.presets import create_default_character
                candidates.append(create_default_character())
            except Exception as e:
                logger.warning(f"[Character] 兜底角色创建失败: {e}")
                candidates.append(Character(id=DEFAULT_CHARACTER_ID, name="助手"))

        for char in candidates:
            cid = getattr(char, "id", None)
            if not cid:
                continue
            self._characters[str(cid)] = char

        if self._characters:
            self._current_id = next(iter(self._characters))
        else:
            fallback = Character(id=DEFAULT_CHARACTER_ID, name="助手")
            self._characters[fallback.id] = fallback
            self._current_id = fallback.id

    # ---------- 查询 ----------

    def get_current(self) -> Optional[Character]:
        with self._rwlock:
            if self._current_id is None:
                return None
            return self._characters.get(self._current_id)

    def get(self, character_id: str) -> Optional[Character]:
        with self._rwlock:
            return self._characters.get(str(character_id))

    def list_characters(self) -> List[Character]:
        with self._rwlock:
            return list(self._characters.values())

    @property
    def current_id(self) -> Optional[str]:
        with self._rwlock:
            return self._current_id

    # ---------- 变更 ----------

    def register(self, character: Character, switch_to: bool = False) -> Character:
        """注册（或覆盖）一个角色。"""
        with self._rwlock:
            self._characters[character.id] = character
            if switch_to or self._current_id is None:
                self._current_id = character.id
        return character

    def switch(self, character_id: str) -> bool:
        """切换当前角色。"""
        with self._rwlock:
            if str(character_id) not in self._characters:
                return False
            self._current_id = str(character_id)
            char = self._characters[self._current_id]
            # 心情名（str）与心情值（int）是两份数据，切换时同步一次
            try:
                char.sync_mood_name()
            except Exception:
                pass
            return True

    def create(self, **kwargs: Any) -> Character:
        """按属性创建角色。"""
        known = {f for f in CharacterAttributes.__dataclass_fields__}
        attr_kwargs = {k: v for k, v in kwargs.items() if k in known and v is not None}

        character_id = str(kwargs.get("id") or "")
        name = str(kwargs.get("name") or attr_kwargs.get("name") or "")

        attributes = CharacterAttributes(
            name=attr_kwargs.pop("name", name), **attr_kwargs
        )
        mood = int(kwargs.get("mood", 4))
        affection = int(kwargs.get("affection", 50))

        character = Character(
            id=character_id,
            name=name,
            attributes=attributes,
            state=CharacterState(mood=mood, affection=affection),
        )
        try:
            character.sync_mood_name()
        except Exception:
            pass
        return self.register(character)

    def update(self, character_id: str, **kwargs: Any) -> Optional[Character]:
        """局部更新角色属性 / 基础信息。"""
        with self._rwlock:
            char = self._characters.get(str(character_id))
            if char is None:
                return None

            if "name" in kwargs and kwargs["name"] is not None:
                char.name = str(kwargs["name"])
                char.attributes.name = char.name

            for key, value in kwargs.items():
                if value is None or key in ("id", "name"):
                    continue
                if hasattr(char.attributes, key):
                    setattr(char.attributes, key, value)

            if kwargs.get("mood") is not None or kwargs.get("affection") is not None:
                try:
                    char.sync_mood_name()
                except Exception:
                    pass

            char.updated_at = time.time()
            return char

    def update_state(self, character_id: str, **kwargs: Any) -> Optional[Character]:
        """更新运行时状态（mood / affection）。"""
        with self._rwlock:
            char = self._characters.get(str(character_id))
            if char is None:
                return None
            if kwargs.get("mood") is not None:
                char.state.mood = int(kwargs["mood"])
            if kwargs.get("affection") is not None:
                char.state.affection = int(kwargs["affection"])
            try:
                char.sync_mood_name()
            except Exception:
                pass
            char.state.touch()
            return char

    def remove(self, character_id: str) -> bool:
        """删除角色；若删的是当前角色，回退到任一其它角色。"""
        with self._rwlock:
            cid = str(character_id)
            if cid not in self._characters:
                return False
            del self._characters[cid]
            if self._current_id == cid:
                self._current_id = next(iter(self._characters), None)
            return True

    # ---------- 序列化 ----------

    def serialize_character(self, character: Character) -> Dict[str, Any]:
        """单个角色序列化（原名 `to_dict(character)`，与管理器级冲突）。"""
        try:
            return character.to_dict()
        except Exception:
            return {
                "id": character.id,
                "name": character.name
            }

    # ---------- 序列化（S3/S5/S6） ----------

    SERIALIZE_VERSION = 1

    def from_dict(self, data: Dict[str, Any]) -> bool:
        """S3：读档恢复。幂等 —— 不覆盖已存在的角色。"""
        if not isinstance(data, dict):
            return False
        version = int(data.get("__version__", 0) or 0)
        if version != self.SERIALIZE_VERSION:
            logger.warning(
                f"[Character] 存档版本 {version} != {self.SERIALIZE_VERSION}，"
                "按当前版本兼容解析"
            )

        restored = 0
        with self._rwlock:
            for item in (data.get("characters") or []):
                if not isinstance(item, dict):
                    continue
                cid = str(item.get("id") or "").strip()
                if not cid:
                    continue
                if cid in self._characters:
                    continue       # 幂等：不动已存在的
                try:
                    from ..characters.models import Character

                    char = Character.from_dict(item) if hasattr(
                        Character, "from_dict") else Character(**item)
                    self._characters[cid] = char
                    restored += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"[Character] 恢复角色 {cid} 失败: {exc}")

            cur = str(data.get("current_id") or "")
            if cur and cur in self._characters:
                self._current_id = cur
            elif not self._current_id and self._characters:
                self._current_id = next(iter(self._characters))
        return restored > 0 or not (data.get("characters") or [])
    
    #给某个角色增加信息
    def add_message(self, character_id: str,role: Literal["user","assistant"], message: str) -> None:
        """给角色增加信息。"""
        with self._rwlock:
            char = self._characters.get(str(character_id))
            if char is None:
                return
            char.state.add_message(role,message)
            #如果大于200条，保存角色消息
            if len(char.state.messages) > 200:
                char.state.messages = char.state.messages[-200:]
    
    def _write(self, character: Character) -> None:
        """写角色状态。"""
        with self._lock:
            self._characters[character.id] = character
            #扔给线程
    
    #增加任务历史
    def add_task_history(self, character_id: str, task: str) -> None:
        """给角色增加任务历史。"""
        with self._rwlock:
            char = self._characters.get(str(character_id))
            if char is None:
                return
            char.state.add_task_history(task)
    
    def get_messages(self, character_id: str, limit: int = 20) -> List[Dict[str, str]]:
        """获取角色最近 limit 条消息。"""
        with self._rwlock:
            char = self._characters.get(str(character_id))
            if char is None:
                return []
            return char.state.get_recent(limit)
    
    #停止保存
    def stop_save(self):
        """停止保存角色状态。"""
        

