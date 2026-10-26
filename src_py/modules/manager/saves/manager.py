import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from ...manager.saves.models import SaveSlot, SaveSlotMeta, Section, default_section, section_from_dict
from ...utils.file import yaml
from ...logger import logger


class SaveSlotManager:
    """存档槽管理"""

    _instance = None
    _lock = threading.RLock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    def __init__(self, base_path: Optional[str] = None) -> None:
        if getattr(self, "_initialized", False):
            return
        if base_path:
            self.base_path = str(base_path)
        else:
            from ...runtime import RuntimePath
            self.base_path = str(RuntimePath.get_user_data_path("saves"))
        self._slots: Dict[str, SaveSlot] = {}
        self._current_slot_id: str = ""
        self._initialized = True
        self._next_id: int = 0
        self._read_index()
        self.ensure_default_slot()


    # ---------- 路径 ----------

    @property
    def _index_path(self) -> str:
        return os.path.join(self.base_path, "index.yaml")

    def _slot_dir(self, slot_id: str) -> str:
        return os.path.join(self.base_path, "slots", str(slot_id))

    def _data_path(self, slot_id: str) -> str:
        return os.path.join(self._slot_dir(slot_id), "data.yaml")

    # ---------- A1：index.yaml ----------

    def _read_index(self) -> None:
        """读 index.yaml（只含元数据，列表展示用）。"""
        self._slots = {}
        try:
            raw = yaml.read_yaml(self._index_path)
        except Exception as exc:  # noqa: BLE001
            raw = {}
        if not isinstance(raw, dict):
            return
        for slot_id, meta in raw.items():
            if not isinstance(meta, dict):
                continue
            self._slots[str(slot_id)] = SaveSlot(
                id=str(slot_id),
                name=str(meta.get("name") or slot_id),
                meta=SaveSlotMeta.from_dict(meta),
                loader=False,
            )

    def _write_index(self) -> None:
        """写 index.yaml。只写元数据 —— 不含 data、不含 sections 这类内部字段。"""
        payload: Dict[str, Any] = {}
        for slot_id, slot in self._slots.items():
            entry = slot.meta.to_dict()
            entry["name"] = slot.name
            payload[slot_id] = entry
            self._next_id = int(slot_id.split("_")[-1])+1
        try:
            yaml.write_yaml(self._index_path, payload)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[SaveSlot] 写 index.yaml 失败: {exc}")

    # ---------- A2：data.yaml ----------

    def _read_data(self, slot: SaveSlot) -> bool:
        """读 `{id}/data.yaml`，槽进入已加载状态。"""
        raw = yaml.read_yaml(self._data_path(slot.id)) or {}
        if not isinstance(raw, dict):
            raw = {}
        for name in Section.all():
            slot.data[name] = section_from_dict(name, raw.get(name))
        slot.loader = True
        return True

    def _write_data(self, slot: SaveSlot) -> bool:
        """写 `{id}/data.yaml`。"""
        os.makedirs(self._slot_dir(slot.id), exist_ok=True)
        payload: Dict[str, Any] = {}
        for name in Section.all():
            value = slot.data.get(name)
            if hasattr(value, "to_dict"):
                payload[name] = value.to_dict()   # type: ignore[union-attr]
            elif isinstance(value, dict):
                payload[name] = value
            else:
                payload[name] = default_section(name)
        try:
            return bool(yaml.write_yaml(self._data_path(slot.id), payload))
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[SaveSlot] 写 data.yaml 失败: {exc}")
            return False

    # ---------- 槽操作 ----------

    def create_slot(self, name: str = "") -> SaveSlot:
        slot_id = f"slot_{self._next_id:03d}"
        slot = SaveSlot(id=slot_id, name=name or slot_id, loader=True)
        for sec in Section.all():
            slot.data[sec] = section_from_dict(sec, default_section(sec))
        base = self._slot_dir(slot_id)
        slot.data[Section.CHARACTERS].path = os.path.join(base, "characters", "roles")
        slot.data[Section.CHAT_HISTORY].path = os.path.join(base, "chat_history", "sessions")
        slot.data[Section.MEMORY].path = os.path.join(base, "memory")
        from ...services.config import ServiceConfig
        slot.data[Section.SERVER] = ServiceConfig().to_dict()

        self._slots[slot_id] = slot
        os.makedirs(slot.data[Section.CHARACTERS].path, exist_ok=True)
        os.makedirs(slot.data[Section.CHAT_HISTORY].path, exist_ok=True)
        self._write_data(slot)
        self._write_index()
        return slot

    def ensure_default_slot(self, name: str = "默认存档") -> SaveSlot:
        """启动时没有存档则自动创建。"""
        with self._lock:
            if self._slots:
                first = next(iter(self._slots.values()))
                if self._current_slot_id:
                    self._current_slot_id = first.id
                return first
            slot = self.create_slot(name=name)
            self._current_slot_id = slot.id
            return slot

    def load_slot(self, slot_id: str) -> bool:
        """加载槽 → 读 data.yaml → 交接路径 → 管理器自己读数据。"""
        with self._lock:
            slot = self._slots.get(slot_id)
            if slot is None:
                return False
            if not self._read_data(slot):
                return False
            self._current_slot_id = slot_id
            return True

    def save_slot(self, slot_id: str = "") -> bool:
        """向各管理器收集路径 → 写 data.yaml → 更新 index.yaml。"""
        with self._lock:
            sid = slot_id or self._current_slot_id
            slot = self._slots.get(sid or "")
            if slot is None:
                return False
            slot.touch()
            ok = self._write_data(slot)
            self._write_index()
            return ok

    def get_slot(self, slot_id: str) -> Optional[SaveSlot]:
        return self._slots.get(slot_id)

    def get_current_slot(self) -> Optional[SaveSlot]:
        if not self._current_slot_id:
            return None
        return self._slots.get(self._current_slot_id)

    def list_metadata(self) -> List[Dict[str, Any]]:
        """列表页用。只读 index.yaml，不打开槽目录。"""
        out = []
        for slot_id, slot in self._slots.items():
            meta = slot.meta.to_dict()
            meta["id"] = slot_id
            meta["name"] = slot.name
            out.append(meta)
        out.sort(key=lambda m: str(m.get("update_time") or ""), reverse=True)
        return out

    def delete_slot(self, slot_id: str) -> bool:
        import shutil

        with self._lock:
            if slot_id not in self._slots:
                return False
            self._slots.pop(slot_id, None)
            if self._current_slot_id == slot_id:
                self._current_slot_id = next(iter(self._slots), "")  # type: ignore[union-attr]
            try:
                shutil.rmtree(self._slot_dir(slot_id), ignore_errors=True)
            except Exception:  # noqa: BLE001
                pass
            self._write_index()
            return True

    def update_meta(self, slot_id: str, **kwargs: Any) -> bool:
        """更新元数据（last_chat / description / snapshot_path）。"""
        with self._lock:
            sid = slot_id or self._current_slot_id
            slot = self._slots.get(sid or "")
            if slot is None:
                return False
            for k, v in kwargs.items():
                if hasattr(slot.meta, k):
                    setattr(slot.meta, k, v)
            slot.touch()
            self._write_index()
            return True

    # ---------- 控制器辅助 ----------

    def get_metadata(self, slot_id: str = "") -> Optional[Dict[str, Any]]:
        with self._lock:
            sid = slot_id or self._current_slot_id
            slot = self._slots.get(sid or "")
        if slot is None:
            return None
        meta = slot.meta.to_dict()
        meta["id"] = slot.id
        meta["name"] = slot.name
        return meta

    def get_section(self, name: str, slot_id: str = "") -> Dict[str, Any]:
        with self._lock:
            sid = slot_id or self._current_slot_id
            slot = self._slots.get(sid or "")
        if slot is None:
            return {}
        value = slot.data.get(name)
        return value.to_dict() if hasattr(value, "to_dict") else dict(value or {})  # type: ignore[union-attr]

    def put_section(self, name: str, value: Dict[str, Any], slot_id: str = "") -> bool:
        with self._lock:
            sid = slot_id or self._current_slot_id
            if not sid:
                return False
            slot = self._slots.get(sid or "")
            if slot is None:
                return False
            slot.data[name] = section_from_dict(name, value)
            slot.touch()
        return self.save_slot(sid)

    def list_slots(self) -> List[Dict[str, Any]]:
        return self.list_metadata()

    def toggle_slot(self, slot_id: str) -> bool:
        return self.load_slot(slot_id)

    def stats(self, slot_id: str = "") -> Dict[str, Any]:
        with self._lock:
            sid = slot_id or self._current_slot_id
            slot = self._slots.get(sid or "")
        if slot is None:
            return {}
        total = 0
        detail = {}
        for name in Section.all():
            size = 0
            p = self._data_path(slot.id)
            if os.path.exists(p):
                try:
                    size = os.path.getsize(p)
                except OSError:
                    size = 0
            detail[name] = {
                "kind": Section.kind(name),
                "size": size
            }
        total = sum(v["size"] for v in detail.values())
        return {
            "slot_id": slot.id,
            "sections": detail,
            "total_size": total
        }

    def sync_from_sessions(self) -> bool:
        return self.save_slot()
    
    @property
    def character(self) -> Dict[str, Any]:
        return self._slots[self._current_slot_id].data.get("character", {})
    
    @property
    def ui(self) -> Dict[str, Any]:
        return self._slots[self._current_slot_id].data.get("ui", {})
    
    @property
    def memory(self) -> Dict[str, Any]:
        return self._slots[self._current_slot_id].data.get("memory", {})
    
    @property
    def chat_history(self) -> Dict[str, Any]:
        return self._slots[self._current_slot_id].data.get("chat_history", {})
    
    @property
    def server(self) -> Dict[str, Any]:
        return self._slots[self._current_slot_id].data.get("server", {})
    
    @server.setter
    def server(self, value: Dict[str, Any]):
        self._slots[self._current_slot_id].data[Section.SERVER] = section_from_dict(Section.SERVER, value)
        self._write_index()


# 落盘前需要脱敏的字段名片段
_SENSITIVE_KEYS = (
    "api_key",
    "apikey",
    "secret",
    "password",
    "token",
    "access_key",
    "passwd"
)


def _sanitize_config(data: Dict[str, Any], _depth: int = 0) -> Dict[str, Any]:
    if _depth > 6 or not isinstance(data, dict):
        return data if isinstance(data, dict) else {}
    out: Dict[str, Any] = {}
    for k, v in data.items():
        key = str(k).lower()
        if any(s in key for s in _SENSITIVE_KEYS) and isinstance(v, str) and v:
            out[k] = "***"
        elif isinstance(v, dict):
            out[k] = _sanitize_config(v, _depth + 1)
        else:
            out[k] = _jsonable(v)
    return out


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(x) for x in value]
    return str(value)

def _compat_update_section(self, name: str, value: Dict[str, Any], slot_id: str = "") -> bool:
    return self.put_section(name, value, slot_id)


def _compat_set_last_chat(self, text: str, slot_id: str = "") -> bool:
    return self.update_meta(slot_id, last_chat=str(text or ""))
