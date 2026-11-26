"""角色管理器

对外接口：
    character_manager.get_current() -> Optional[Character]
    character_manager.get(id)       -> Optional[Character]
    character_manager.switch(id)    -> bool
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from .. import runtime
from ..logger import logger
from .models import Character, CharacterAttributes, CharacterState

DEFAULT_CHARACTER_ID = "qingmei"
_MOOD_DEFAULT = 4
_AFFECTION_DEFAULT = 50
_AFFECTION_MIN, _AFFECTION_MAX = 0, 100


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


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
        #: 运行态是否发生变更，供存档域判断是否值得导出 section。
        self._dirty = False

    # ---------- 初始化 ----------

    def load_characters(self, path: str = "") -> None:
        """启动加载：显式 path 或内置模板，产出可用的默认注册表。

        PR-2：不再从存档槽的 `characters.path` 指针读角色 —— 那是旧的
        "路径即存档"模型。存档里的角色运行态由 `CharacterOriginator`
        通过 `from_dict()` 注入，启动加载只负责保证注册表非空。
        """
        from .presets import load_character

        source = str(path or "").strip()
        if not source:
            try:
                source = str(runtime.RuntimePath.get_template_path("roles.yaml"))
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[Character] 内置模板路径不可用: {exc}")
                source = ""

        candidate = Path(source) if source else None
        characters: List[Character] = (
            load_character(str(candidate)) if candidate is not None else []
        )

        with self._rwlock:
            if characters:
                self._characters = {str(char.id): char for char in characters}
                self._save_path = str(candidate)
                logger.info(
                    f"[Character] 已加载 {len(self._characters)} 个角色: {source}"
                )
            else:
                self._load_defaults()
                logger.warning("[Character] 角色模板不可用，使用默认角色")
            if self._current_id not in self._characters:
                self._current_id = next(iter(self._characters), None)
            self._dirty = False

    def _load_defaults(self) -> None:
        """预置默认角色，保证 `get_current()` 永远可用。"""
        candidates: List[Any] = []
        try:
            from .presets import create_defaults

            produced = create_defaults()
            candidates.extend(produced if isinstance(produced, (list, tuple)) else [])
        except Exception as e:
            logger.warning(f"[Character] 默认角色创建失败: {e}")

        if not candidates:
            try:
                from .presets import create_default_character

                candidates.append(create_default_character())
            except Exception as e:
                logger.warning(f"[Character] 兜底角色创建失败: {e}")
                candidates.append(Character(id=DEFAULT_CHARACTER_ID, name="助手"))

        for char in candidates:
            cid = getattr(char, "id", None)
            if not cid:
                continue
            self._characters[str(cid)] = char

        if not self._characters:
            fallback = Character(id=DEFAULT_CHARACTER_ID, name="助手")
            self._characters[fallback.id] = fallback
        self._current_id = next(iter(self._characters))

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

    @property
    def is_dirty(self) -> bool:
        with self._rwlock:
            return self._dirty

    def clear_dirty(self) -> None:
        with self._rwlock:
            self._dirty = False

    # ---------- 变更 ----------

    def register(self, character: Character, switch_to: bool = False) -> Character:
        """注册（或覆盖）一个角色。"""
        with self._rwlock:
            self._characters[character.id] = character
            if switch_to or self._current_id is None:
                self._current_id = character.id
            self._dirty = True
        return character

    def switch(self, character_id: str) -> bool:
        """切换当前角色。"""
        with self._rwlock:
            cid = str(character_id)
            if cid not in self._characters:
                return False
            self._current_id = cid
            char = self._characters[cid]
            # 心情名（str）与心情值（int）是两份数据，切换时同步一次
            char.sync_mood_name()
            self._dirty = True
            return True

    def create(self, **kwargs: Any) -> Character:
        """按属性创建角色。mood/affection 只属于 state，不写进 attributes。"""
        known = {f for f in CharacterAttributes.__dataclass_fields__} - {
            "mood", "affection_level"
        }
        attr_kwargs = {k: v for k, v in kwargs.items() if k in known and v is not None}

        character_id = str(kwargs.get("id") or "")
        name = str(kwargs.get("name") or attr_kwargs.get("name") or "")
        attributes = CharacterAttributes(
            name=str(attr_kwargs.pop("name", name) or name), **attr_kwargs
        )
        mood = _safe_int(kwargs.get("mood", _MOOD_DEFAULT), _MOOD_DEFAULT)
        affection = _clamp(
            _safe_int(kwargs.get("affection", _AFFECTION_DEFAULT), _AFFECTION_DEFAULT),
            _AFFECTION_MIN, _AFFECTION_MAX,
        )
        attributes.affection_level = affection

        character = Character(
            id=character_id,
            name=name,
            attributes=attributes,
            state=CharacterState(mood=mood, affection=affection),
        )
        character.sync_mood_name()
        return self.register(character)

    def update(self, character_id: str, **kwargs: Any) -> Optional[Character]:
        """局部更新角色属性 / 基础信息 / 运行时数值。"""
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
                if key == "mood":
                    char.state.mood = _safe_int(value, char.state.mood)
                elif key == "affection":
                    char.state.affection = _clamp(
                        _safe_int(value, char.state.affection),
                        _AFFECTION_MIN, _AFFECTION_MAX,
                    )
                    char.attributes.affection_level = char.state.affection
                elif key == "affection_level":
                    char.attributes.affection_level = _clamp(
                        _safe_int(value, char.attributes.affection_level),
                        _AFFECTION_MIN, _AFFECTION_MAX,
                    )
                elif key == "avatar":
                    char.avatar = str(value)
                elif hasattr(char.attributes, key):
                    setattr(char.attributes, key, value)

            char.sync_mood_name()
            char.updated_at = time.time()
            char.state.touch()
            self._dirty = True
            return char

    def update_state(self, character_id: str, **kwargs: Any) -> Optional[Character]:
        """更新运行时状态（mood / affection）。非法值回落到原值，不抛 500。"""
        with self._rwlock:
            char = self._characters.get(str(character_id))
            if char is None:
                return None
            if kwargs.get("mood") is not None:
                char.state.mood = _safe_int(kwargs["mood"], char.state.mood)
            if kwargs.get("affection") is not None:
                char.state.affection = _clamp(
                    _safe_int(kwargs["affection"], char.state.affection),
                    _AFFECTION_MIN, _AFFECTION_MAX,
                )
            char.sync_mood_name()
            char.attributes.affection_level = char.state.affection
            char.state.touch()
            self._dirty = True
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
            self._dirty = True
            return True

    # ---------- 序列化 ----------

    def serialize_character(self, character: Character) -> Dict[str, Any]:
        """单个角色序列化（原名 `to_dict(character)`，与管理器级冲突）。"""
        try:
            return character.to_dict()
        except Exception:
            return {"id": character.id, "name": character.name}

    SERIALIZE_VERSION = 1

    def to_dict(self) -> Dict[str, Any]:
        """管理器级完整快照，供存档域 Originator 导出（PR-2 接线）。"""
        with self._rwlock:
            return {
                "__version__": self.SERIALIZE_VERSION,
                "characters": [c.to_dict() for c in self._characters.values()],
                "current_id": self._current_id or "",
            }

    def from_dict(self, data: Dict[str, Any]) -> bool:
        """读档恢复：**原子全量替换**当前注册表。

        原实现的「幂等：不覆盖已存在的角色」会让恢复形同虚设 —— 启动后
        注册表已有默认角色，存档里的角色状态一条都进不来。
        """
        if not isinstance(data, dict):
            return False
        version = _safe_int(data.get("__version__", 0), 0)
        if version != self.SERIALIZE_VERSION:
            # PR-2：不保留兼容解析。版本不符即整域拒绝，恢复事务会
            # 在 Prepare 阶段停下来，运行态保持原样。
            logger.warning(
                f"[Character] 存档版本 {version} != {self.SERIALIZE_VERSION}，拒绝恢复"
            )
            return False

        raw_items = data.get("characters") or []
        if not isinstance(raw_items, (list, tuple)):
            return False
        restored: Dict[str, Character] = {}
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            cid = str(item.get("id") or "").strip()
            if not cid:
                continue
            try:
                char = Character.from_dict(item)
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[Character] 恢复角色 {cid} 失败: {exc}")
                continue
            restored[char.id or cid] = char

        if not restored:
            return False

        cur = str(data.get("current_id") or "")
        with self._rwlock:
            self._characters = restored
            self._current_id = cur if cur in restored else next(iter(restored))
            self._dirty = False
        return True

    # ---------- 角色消息 / 任务历史 ----------

    def add_message(
        self, character_id: str, role: Literal["user", "assistant"], message: str
    ) -> None:
        """给角色增加信息；裁剪由 CharacterState 按 max_memory 统一处理。"""
        with self._rwlock:
            char = self._characters.get(str(character_id))
            if char is None:
                return
            char.state.add_message(role, message)
            self._dirty = True

    def _write(self, character: Character) -> None:
        """登记角色状态变更（脏标记），不再与存档系统双写。"""
        with self._rwlock:
            self._characters[character.id] = character
            self._dirty = True

    def add_task_history(self, character_id: str, task: str) -> None:
        """给角色增加任务历史。"""
        with self._rwlock:
            char = self._characters.get(str(character_id))
            if char is None:
                return
            char.state.add_task_history(task)
            self._dirty = True

    def get_messages(self, character_id: str, limit: int = 20) -> List[Dict[str, str]]:
        """获取角色最近 limit 条消息。"""
        with self._rwlock:
            char = self._characters.get(str(character_id))
            if char is None:
                return []
            return char.state.get_recent(limit)

    def stop_save(self) -> None:
        """停止保存角色状态：清空脏标记，幂等且不抛异常。"""
        with self._rwlock:
            self._dirty = False
