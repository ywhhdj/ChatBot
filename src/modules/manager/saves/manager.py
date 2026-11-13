import json
import os
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from ...manager.saves.models import SaveSlot, SaveSlotMeta, Section, default_section, section_from_dict
from ...utils.file import yaml
from ...utils.file.atomic import atomic_write_json, atomic_write_yaml, safe_join

_SLOT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _safe_slot_id(slot_id: Any) -> str:
    """槽 id 会拼进文件路径，必须白名单校验，杜绝 ../ 逃逸。"""
    value = str(slot_id or "").strip()
    if not _SLOT_ID_RE.fullmatch(value):
        raise ValueError(f"非法 slot_id: {value!r}（只允许字母数字 _ -，长度 1-64）")
    return value
from ...logger import logger
from . import memento
from . import binary


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
        return safe_join(self.base_path, "slots", _safe_slot_id(slot_id))

    def _data_path(self, slot_id: str) -> str:
        return safe_join(self.base_path, f"{_safe_slot_id(slot_id)}.save")

    def _legacy_data_path(self, slot_id: str) -> str:
        return safe_join(
            self.base_path, "slots", _safe_slot_id(slot_id), "data.yaml"
        )

    # ---------- index.yaml ----------

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
            try:
                sid = _safe_slot_id(slot_id)
            except ValueError:
                logger.warning(f"[SaveSlot] 跳过非法槽 id: {slot_id!r}")
                continue
            self._slots[sid] = SaveSlot(
                id=sid,
                name=str(meta.get("name") or sid),
                meta=SaveSlotMeta.from_dict(meta),
                loader=False,
            )

    def _write_index(self) -> None:
        """写 index.yaml。只写元数据 —— 不含 data、不含 sections 这类内部字段。"""
        payload: Dict[str, Any] = {}
        highest = 0
        for slot_id, slot in self._slots.items():
            entry = slot.meta.to_dict()
            entry["name"] = slot.name
            payload[slot_id] = entry
            match = re.fullmatch(r"slot_(\d+)", str(slot_id))
            if match:
                highest = max(highest, int(match.group(1)))
        self._next_id = highest + 1
        try:
            atomic_write_yaml(self._index_path, payload)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[SaveSlot] 写 index.yaml 失败: {exc}")
            raise

    # ---------- .save 二进制存档 ----------

    def _read_data(self, slot: SaveSlot) -> bool:
        """读槽的当前状态。优先二进制，读不到再回退旧 data.yaml。

        二进制校验失败**直接返回 False**，绝不"尽力解析"出一个缺字段的槽 ——
        静默降级比明确拒绝危险得多：用户会以为存档完好，直到恢复时才发现。
        """
        path = self._data_path(slot.id)
        if os.path.exists(path):
            archive, code, msg = binary.read_archive(path)
            if archive is None:
                logger.error(
                    f"[SaveSlot] 存档 {slot.id} 校验失败 [{code.value}]: {msg}"
                )
                return False
            for name in Section.all():
                slot.data[name] = section_from_dict(name, archive.section(name))
            slot.loader = True
            return True

        legacy = self._legacy_data_path(slot.id)
        if os.path.exists(legacy):
            try:
                raw = yaml.read_yaml(legacy) or {}
            except Exception as exc:  # noqa: BLE001
                logger.error(f"[SaveSlot] 旧 data.yaml 读取失败: {exc}")
                return False
            if not isinstance(raw, dict):
                raw = {}
            for name in Section.all():
                slot.data[name] = section_from_dict(name, raw.get(name))
            slot.loader = True
            return True

        return False

    def _write_data(self, slot: SaveSlot) -> bool:
        """写 `saves/<id>.save`。原子写 + 整体/分段双重校验和。
        """
        os.makedirs(self.base_path, exist_ok=True)
        # 路径指针段仍需要各自的目录（角色/会话/记忆真实数据归各自管理器）
        os.makedirs(self._slot_dir(slot.id), exist_ok=True)

        payload: Dict[str, Any] = {}
        for name in Section.all():
            value = slot.data.get(name)
            if hasattr(value, "to_dict"):
                item = value.to_dict()   # type: ignore[union-attr]
            elif isinstance(value, dict):
                item = dict(value)
            else:
                item = default_section(name)
            if name == Section.SERVER:
                item = _sanitize_config(item if isinstance(item, dict) else {})
            payload[name] = item

        create_time = getattr(slot.meta, "create_time", None)
        created_at = (
            float(create_time.timestamp())  # type: ignore[union-attr]
            if hasattr(create_time, "timestamp") else 0.0
        )
        ok = binary.write_archive(
            self._data_path(slot.id),
            slot_id=slot.id,
            name=slot.name,
            sections=payload,
            kinds={n: Section.kind(n) for n in Section.all()},
            reference_only={n: n in Section.PATH_SECTIONS for n in Section.all()},
            created_at=created_at,
            meta={"section_count": len(payload)},
        )
        if not ok:
            logger.error(f"[SaveSlot] 写 .save 失败: {slot.id}")
        return ok

    # ---------- 槽操作 ----------

    def create_slot(self, name: str = "", slot_id: Optional[str] = None) -> SaveSlot:
        """新建槽。

        controller 一直按 `create_slot(name, slot_id)` 调用，旧签名只收 1 个
        参数，新建存档必 TypeError。自定义 id 必须先过白名单校验。
        """
        sid = _safe_slot_id(slot_id) if slot_id else f"slot_{self._next_id:03d}"
        with self._lock:
            if sid in self._slots:
                return self._slots[sid]
        slot = SaveSlot(id=sid, name=name or sid, loader=True)
        for sec in Section.all():
            slot.data[sec] = section_from_dict(sec, default_section(sec))
        base = self._slot_dir(sid)
        slot.data[Section.CHARACTERS].path = safe_join(base, "characters", "roles")
        slot.data[Section.CHAT_HISTORY].path = safe_join(base, "chat_history", "sessions")
        slot.data[Section.MEMORY].path = safe_join(base, "memory")
        from ...services.config import ServiceConfig
        slot.data[Section.SERVER] = ServiceConfig().to_dict()

        with self._lock:
            self._slots[sid] = slot
        os.makedirs(slot.data[Section.CHARACTERS].path, exist_ok=True)
        os.makedirs(slot.data[Section.CHAT_HISTORY].path, exist_ok=True)
        self._write_data(slot)
        self._write_index()
        return slot

    def ensure_default_slot(self, name: str = "默认存档") -> SaveSlot:
        """启动时没有存档则自动创建。"""
        with self._lock:
            if self._slots:
                if not self._current_slot_id or self._current_slot_id not in self._slots:
                    self._current_slot_id = next(iter(self._slots))
                return self._slots[self._current_slot_id]
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

        try:
            sid = _safe_slot_id(slot_id)
        except ValueError:
            return False
        main_file = self._data_path(sid)
        legacy_file = self._legacy_data_path(sid)
        with self._lock:
            if sid not in self._slots:
                return False
            self._slots.pop(sid, None)
            if self._current_slot_id == sid:
                self._current_slot_id = next(iter(self._slots), "")
            try:
                shutil.rmtree(self._slot_dir(sid), ignore_errors=True)
            except Exception:  # noqa: BLE001
                pass
            # 旧实现只删 slots/<id>/ 目录，主存档 <id>.save 与旧 data.yaml
            # 永远留在磁盘上，越删越多且旧 id 复用会读到陈旧数据。
            for path in (main_file, legacy_file, main_file + ".tmp"):
                try:
                    os.unlink(path)
                except OSError:
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

    def sync_from_sessions(self, session_id: str = "") -> bool:
        """把会话管理器的会话与消息同步进当前存档槽。"""
        from ..session.manager import SessionManager

        sm = SessionManager()
        sm.flush()
        entries = sm.list()
        if session_id:
            try:
                wanted = _safe_slot_id(session_id)
            except ValueError:
                return False
            entries = [e for e in entries if str(e.get("id")) == wanted]
        with self._lock:
            sid = self._current_slot_id
            slot = self._slots.get(sid)
        if slot is None:
            return False

        current = self.get_section(Section.CHAT_HISTORY, sid)
        base = str(current.get("path") or "") or safe_join(
            self._slot_dir(sid), "chat_history", "sessions"
        )
        os.makedirs(base, exist_ok=True)
        written: List[str] = []
        for entry in entries:
            sess_id = str(entry.get("id") or "")
            try:
                target = safe_join(base, f"{_safe_slot_id(sess_id)}.json")
            except ValueError:
                continue
            sess = sm.get(sess_id)
            messages = list(getattr(sess, "messages", None) or []) if sess else []
            atomic_write_json(target, {"meta": entry, "messages": messages})
            written.append(sess_id)

        slot.data[Section.CHAT_HISTORY] = section_from_dict(
            Section.CHAT_HISTORY,
            {"path": base, "recent_sessions": json.dumps(written, ensure_ascii=False)},
        )
        slot.touch()
        return self.save_slot(sid)

    def restore_to_sessions(self) -> Dict[str, Any]:
        """反向同步：从当前存档槽的 chat_history 恢复到会话管理器。

        对应前端 `restoreToSessions()`（POST /save/slots/restore）。
        只读存档目录，不改动存档本身。
        """
        from ..session.manager import SessionManager

        with self._lock:
            sid = self._current_slot_id
        if not sid or not self.load_slot(sid):
            return {"ok": False, "restored": 0, "sessions": [], "reason": "当前存档不可用"}
        with self._lock:
            slot = self._slots.get(sid)
        if slot is None:
            return {"ok": False, "restored": 0, "sessions": [], "reason": "槽不存在"}
        current = self.get_section(Section.CHAT_HISTORY, sid)
        base = str(current.get("path") or "")
        if not base or not os.path.isdir(base):
            return {"ok": True, "restored": 0, "sessions": [], "reason": "无会话快照"}

        sm = SessionManager()
        restored: List[str] = []
        for name in sorted(os.listdir(base)):
            if not name.endswith(".json"):
                continue
            try:
                with open(safe_join(base, name), "r", encoding="utf-8") as fh:
                    payload = json.load(fh)
            except Exception:  # noqa: BLE001 - 单个坏快照跳过
                continue
            meta = payload.get("meta") if isinstance(payload, dict) else {}
            meta = meta if isinstance(meta, dict) else {}
            sess_id = str(meta.get("id") or name[:-5])
            try:
                sess = sm.get(sess_id) or sm.create(
                    name=str(meta.get("name") or sess_id),
                    character_id=str(meta.get("character_id") or ""),
                    session_id=sess_id,
                )
            except ValueError:
                continue
            messages = payload.get("messages") if isinstance(payload, dict) else []
            sess.messages = [dict(m) for m in messages if isinstance(m, dict)] if isinstance(messages, list) else []
            sess.updated_at = time.time()
            sm.save_sync(sess)
            restored.append(sess_id)
        return {"ok": True, "restored": len(restored), "sessions": restored}

    # ---------- 快照----------

    @property
    def snapshots_root(self) -> str:
        return self.base_path

    def _next_revision(self, slot_id: str) -> str:
        """下一个 revision 号。基于已有 revision 最大值 +1。

        不基于目录数量：删掉中间 revision 后序号会重用，
        而"同号不同内容"会让恢复预演的结论失去意义。
        """
        existing = memento.list_revisions(self.base_path, slot_id)
        max_n = 0
        for item in existing:
            raw = str(item.get("revision", ""))
            digits = "".join(ch for ch in raw if ch.isdigit())
            if digits:
                max_n = max(max_n, int(digits))
        return f"rev-{max_n + 1:06d}"

    def create_snapshot(
        self,
        slot_id: str = "",
        consistency_level: Optional["memento.ConsistencyLevel"] = None,
        *,
        branch_id: str = "main",
        label: str = "",
        trigger: str = "manual",
        parent_revision: str = "",
    ) -> Dict[str, Any]:
        """为槽创建一个快照 revision"""
        with self._lock:
            sid = slot_id or self._current_slot_id
            slot = self._slots.get(sid or "")
            if slot is None:
                return {
                    "ok": False,
                    "code": memento.RejectCode.MISSING_FIELD.value,
                    "message": f"槽不存在: {sid}"
                }

            level = consistency_level or memento.ConsistencyLevel.CHECKPOINT
            # 自然形成分支，不覆盖旧 revision。
            parent = parent_revision or self._current_revision(sid) or ""
            manifest = memento.new_manifest(
                slot_id=sid,
                revision=self._next_revision(sid),
                parent_revision=parent,
                consistency_level=level,
                redactions=("provider_secrets",),
                branch_id=branch_id,
                label=label,
                trigger=trigger,
            )

            staging = memento.prepare_staging(self.base_path, sid, manifest.operation_id)

            entries = []
            for name in Section.all():
                value = slot.data.get(name)
                payload = value.to_dict() if hasattr(value, "to_dict") else   dict(value or {})
                # 路径指针段不能声称是完整数据
                reference_only = name in Section.PATH_SECTIONS
                entries.append(memento.write_section(
                    staging, name, payload,
                    kind=Section.kind(name),
                    reference_only=reference_only,
                ))

            # 写 manifest（status=prepared）
            prepared = manifest.with_sections(tuple(entries))
            atomic_write_json(
                memento.manifest_path(staging), prepared.to_dict()
            )

            published, code, msg = memento.publish_revision(
                self.base_path, sid, staging, prepared.revision
            )
            if published is None:
                return {
                    "ok": False,
                    "code": code.value,
                    "message": msg
                }

            return {
                "ok": True,
                "code": memento.RejectCode.OK.value,
                "revision": published.revision,
                "consistency_level": published.effective_level().value,
                "declared_level": published.consistency_level,
                "sections": sorted(e.name for e in published.sections),
                "parent_revision": published.parent_revision,
                "branch_id": published.branch_id,
                "label": published.label,
                "trigger": published.trigger,
                "warnings": (
                    ["声明等级与实际不符，已按实际等级记录"]
                    if published.level_is_overstated() else []
                ),
            }

    def _current_revision(self, slot_id: str) -> str:
        current, _, _ = memento.read_current(self.base_path, slot_id)
        return current.revision if current else ""

    def list_snapshots(self, slot_id: str = "") -> List[Dict[str, Any]]:
        sid = slot_id or self._current_slot_id
        if not sid:
            return []
        return memento.list_revisions(self.base_path, sid)

    def preview_restore(
        self, slot_id: str = "", revision: str = "", *, memory_probe=None
    ) -> Dict[str, Any]:
        """恢复预演。**只读**，不改任何运行态（B1-03 / S2-04）。"""
        sid = slot_id or self._current_slot_id
        if not sid:
            return {
                "ok": False,
                "code": memento.RejectCode.MISSING_FIELD.value,
                "message": "未指定槽"
            }
        plan = memento.preview_restore(
            self.base_path, sid, revision, memory_probe=memory_probe
        )
        result = plan.as_dict()
        result["ok"] = plan.safe
        return result

    def revision_graph(self, slot_id: str = "") -> Dict[str, Any]:
        """revision DAG：节点/边/分支/叶子/current。只读。"""
        sid = slot_id or self._current_slot_id
        if not sid:
            return {
                "slot_id": "",
                "nodes": [],
                "edges": [],
                "branches": {},
                "heads": [], 
                "current": "",
                "protected": ""
            }
        return memento.revision_graph(self.base_path, sid)
    
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


from ...constaints import SENSITIVE_KEYS


def _sanitize_config(data: Dict[str, Any], _depth: int = 0) -> Dict[str, Any]:
    if _depth > 6 or not isinstance(data, dict):
        return data if isinstance(data, dict) else {}
    out: Dict[str, Any] = {}
    for k, v in data.items():
        key = str(k).lower()
        if any(s in key for s in SENSITIVE_KEYS) and isinstance(v, str) and v:
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
