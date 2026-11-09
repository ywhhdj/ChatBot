"""会话存档管理（session-scoped，线程安全）

对外 API 与 controller / chat.py 的调用形状保持一致。
"""

from __future__ import annotations

import atexit
import os
import re
import shutil
import threading
import time
from collections import OrderedDict
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Set, Tuple

from .models import RoundRecord, Session
from ...logger import logger
from ...runtime import StandardPaths
from ...utils.file import pickle, yaml
from ...utils.file.atomic import atomic_write_json, safe_join
from ...utils.util import id_generator

# 单会话保留的最近消息条数
MAX_SESSION_MESSAGES = 200
#: 内存中最多缓存多少个会话（LRU，超出时已落盘的才淘汰）
MAX_CACHED_SESSIONS = 64
#: 脏数据合并落盘的窗口 / 条数阈值
FLUSH_INTERVAL = 1.5
FLUSH_DIRTY_THRESHOLD = 8
#: 每会话文件锁表上限，防止 id 无限枚举撑爆内存
MAX_FILE_LOCKS = 128

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
#: 旧目录里属于存档槽、绝不能被会话迁移/列表误认的文件
_NON_SESSION_NAMES = {"index.yaml"}
DEFAULT_SESSION_ID = "default"


def _safe_id(session_id: Any) -> str:
    """会话 id 会直接进文件名，必须白名单校验。"""
    value = str(session_id or "").strip()
    if not _ID_RE.fullmatch(value):
        raise ValueError(f"非法 session_id: {value!r}（只允许字母数字 _ -，长度 1-64）")
    return value


class SessionManager:
    _instance = None
    _cls_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._cls_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        root = StandardPaths.get_user_data_dir()
        self.base_path = os.path.join(str(root), "sessions")
        os.makedirs(self.base_path, exist_ok=True)
        self._legacy_path = os.path.join(str(root), "saves")
        self._sessions: "OrderedDict[str, Session]" = OrderedDict()
        self._current_session_id: Optional[str] = None
        self._rounds: Dict[str, RoundRecord] = {}
        self._dirty: Set[str] = set()
        self._dirty_since: Dict[str, float] = {}
        self._file_locks: "OrderedDict[str, threading.Lock]" = OrderedDict()
        self._lock = threading.RLock()
        self._initialized = True
        self._migrate_legacy()
        self._restore_current_pointer()
        atexit.register(self._atexit_flush)

    # ------------------------------------------------------------------
    # 路径与锁
    # ------------------------------------------------------------------

    def yaml_path(self, session_id: str) -> str:
        return safe_join(self.base_path, f"{_safe_id(session_id)}.yaml")

    def pkl_path(self, session_id: str) -> str:
        return safe_join(self.base_path, f"{_safe_id(session_id)}.messages.pkl")

    def _pointer_path(self) -> str:
        return safe_join(self.base_path, "current.json")

    def _file_lock(self, session_id: str) -> threading.Lock:
        with self._lock:
            lock = self._file_locks.get(session_id)
            if lock is None:
                lock = threading.Lock()
                self._file_locks[session_id] = lock
                while len(self._file_locks) > MAX_FILE_LOCKS:
                    self._file_locks.popitem(last=False)
            else:
                self._file_locks.move_to_end(session_id)
            return lock

    def _migrate_legacy(self) -> None:
        try:
            if not os.path.isdir(self._legacy_path):
                return
            for name in os.listdir(self._legacy_path):
                if not name.endswith(".yaml") or name in _NON_SESSION_NAMES:
                    continue
                sid = name[:-5]
                try:
                    _safe_id(sid)
                except ValueError:
                    continue
                src = os.path.join(self._legacy_path, name)
                dst = safe_join(self.base_path, name)
                if not os.path.isfile(src) or os.path.exists(dst):
                    continue
                shutil.move(src, dst)
                for suffix in (".messages.pkl", ".messages.pkl.tmp", ".yaml.tmp"):
                    old = os.path.join(self._legacy_path, sid + suffix)
                    if os.path.isfile(old):
                        shutil.move(old, safe_join(self.base_path, sid + suffix))
                logger.info(f"[Session] 已从旧目录迁移会话 {sid}")
        except Exception as exc:  # noqa: BLE001 - 迁移是尽力而为
            logger.warning(f"[Session] 旧会话迁移失败: {exc}")

    def _restore_current_pointer(self) -> None:
        try:
            import json

            path = self._pointer_path()
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as fh:
                    sid = str((json.load(fh) or {}).get("id") or "")
                if sid and os.path.isfile(self.yaml_path(sid)):
                    self._current_session_id = sid
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[Session] current 指针读取失败: {exc}")

    def _write_pointer(self, sid: str) -> None:
        try:
            atomic_write_json(self._pointer_path(), {"id": sid})
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[Session] current 指针写入失败: {exc}")

    # ------------------------------------------------------------------
    # 磁盘读写
    # ------------------------------------------------------------------

    @staticmethod
    def _meta(sess: Session) -> Dict[str, Any]:
        """元信息（不含消息体），用于 yaml 与列表页。"""
        data = asdict(sess)
        data.pop("messages", None)
        data["message_count"] = len(sess.messages)
        return data

    def _write_snapshot(self, session_id: str, meta: Dict[str, Any], messages: List[Dict]) -> None:
        """原子双写：先 pkl 再 yaml，yaml 是提交点。"""
        yp = self.yaml_path(session_id)
        pp = self.pkl_path(session_id)
        tmp_y, tmp_p = yp + ".tmp", pp + ".tmp"
        with self._file_lock(session_id):
            try:
                yaml.write_yaml(tmp_y, dict(meta))
                pickle.write_pickle(tmp_p, list(messages))
                os.replace(tmp_p, pp)
                os.replace(tmp_y, yp)
            except BaseException:
                for tmp in (tmp_y, tmp_p):
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass
                raise

    def _read(self, session_id: str) -> Optional[Session]:
        yp = self.yaml_path(session_id)
        if not os.path.isfile(yp):
            return None
        try:
            raw = yaml.read_yaml(yp)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[Session] 读取 {yp} 失败: {exc}")
            return None
        if not isinstance(raw, dict):
            return None
        messages: List[Dict] = []
        pp = self.pkl_path(session_id)
        if os.path.isfile(pp):
            try:
                data = pickle.read_pickle(pp)
                if isinstance(data, list):
                    messages = [dict(m) for m in data if isinstance(m, dict)]
            except Exception as exc:  # noqa: BLE001 - 消息损坏不阻塞元信息
                logger.warning(f"[Session] 读取消息 {pp} 失败: {exc}")
        raw["messages"] = messages
        return Session.from_dict(raw)

    def _cache(self, sess: Session) -> Session:
        with self._lock:
            self._sessions[sess.id] = sess
            self._sessions.move_to_end(sess.id)
            while len(self._sessions) > MAX_CACHED_SESSIONS:
                evict_id, _ = next(iter(self._sessions.items()))
                if evict_id in self._dirty:
                    break
                self._sessions.popitem(last=False)
        return sess

    # ------------------------------------------------------------------
    # 轮次记录（按 session 分桶）
    # ------------------------------------------------------------------

    @staticmethod
    def _route_value(route: Any) -> str:
        return str(getattr(route, "value", route) or "pure_chat")

    def _round_key(self, session_id: str = "") -> str:
        if session_id:
            return _safe_id(session_id)
        with self._lock:
            return self._current_session_id or DEFAULT_SESSION_ID

    def begin_round(
        self,
        user_input: str,
        character_id: str = "",
        route: str = "pure_chat",
        session_id: str = "",
    ) -> RoundRecord:
        """一轮 = 用户发起 → 路由 → （轮内可能多次工具调用）→ 回复结束。"""
        sid = self._round_key(session_id)
        rec = RoundRecord(
            session_id=sid,
            character_id=character_id or "",
            route=self._route_value(route),
            user_input=user_input,
            started_at=time.time(),
        )
        with self._lock:
            self._rounds[sid] = rec
        return rec

    def current_round(self, session_id: str = "") -> Optional[RoundRecord]:
        with self._lock:
            return self._rounds.get(self._round_key(session_id))

    def record_tool_call(self, item: Dict[str, Any], session_id: str = "") -> None:
        with self._lock:
            rec = self._rounds.get(self._round_key(session_id))
        if rec is not None:
            rec.tool_calls.append(dict(item or {}))

    def set_route(self, route: Any, session_id: str = "") -> None:
        with self._lock:
            rec = self._rounds.get(self._round_key(session_id))
        if rec is not None:
            rec.route = self._route_value(route)

    def end_round(self, reply: str = "", session_id: str = "") -> Optional[RoundRecord]:
        sid = self._round_key(session_id)
        with self._lock:
            rec = self._rounds.pop(sid, None)
        if rec is None:
            return None
        rec.reply = reply
        rec.ended_at = time.time()
        return rec

    # ------------------------------------------------------------------
    # 会话 CRUD
    # ------------------------------------------------------------------

    def create(
        self,
        name: str,
        character_id: str,
        session_id: Optional[str] = None,
    ) -> Session:
        sid = _safe_id(session_id) if session_id else id_generator("session_")
        with self._lock:
            existing = self._sessions.get(sid)
        if existing is not None:
            return existing
        if os.path.isfile(self.yaml_path(sid)):
            loaded = self._read(sid)
            if loaded is not None:
                return self._cache(loaded)
        sess = Session(
            id=sid,
            name=str(name or sid),
            character_id=str(character_id or ""),
            created_at=time.time(),
            updated_at=time.time(),
            messages=[],
            memory_ids=[],
        )
        self._cache(sess)
        self._write_snapshot(sid, self._meta(sess), [])
        return sess

    def get(self, session_id: str) -> Optional[Session]:
        try:
            sid = _safe_id(session_id)
        except ValueError:
            return None
        with self._lock:
            sess = self._sessions.get(sid)
            if sess is not None:
                self._sessions.move_to_end(sid)
                return sess
        loaded = self._read(sid)
        if loaded is not None:
            return self._cache(loaded)
        # chat.py 在初始化时直接 get("default")；缺了它整条对话链路拿不到会话
        if sid == DEFAULT_SESSION_ID:
            return self.create(DEFAULT_SESSION_ID, "", session_id=DEFAULT_SESSION_ID)
        return None

    def list(self) -> List[Dict[str, Any]]:
        """列表页：只读元信息 yaml，不打开任何消息 pkl。"""
        out: Dict[str, Dict[str, Any]] = {}
        try:
            for name in os.listdir(self.base_path):
                if not name.endswith(".yaml") or name in _NON_SESSION_NAMES:
                    continue
                sid = name[:-5]
                try:
                    _safe_id(sid)
                except ValueError:
                    continue
                try:
                    raw = yaml.read_yaml(safe_join(self.base_path, name))
                except Exception:  # noqa: BLE001 - 单个坏文件跳过
                    continue
                if isinstance(raw, dict):
                    out[sid] = raw
        except OSError as exc:
            logger.warning(f"[Session] 列出会话失败: {exc}")
        with self._lock:
            for sid, sess in self._sessions.items():
                out[sid] = self._meta(sess)
        items: List[Dict[str, Any]] = []
        for sid, raw in out.items():
            meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
            items.append({
                "id": sid,
                "name": str(raw.get("name") or sid),
                "character_id": str(raw.get("character_id") or ""),
                "created_at": float(raw.get("created_at") or 0.0),
                "updated_at": float(raw.get("updated_at") or 0.0),
                "message_count": int(raw.get("message_count") or 0),
                "metadata": meta,
            })
        items.sort(key=lambda x: x["updated_at"], reverse=True)
        return items

    def get_current(self) -> Optional[Session]:
        with self._lock:
            sid = self._current_session_id
        if sid:
            sess = self.get(sid)
            if sess is not None:
                return sess
        items = self.list()
        if items:
            return self.get(str(items[0]["id"]))
        sess = self.get(DEFAULT_SESSION_ID)
        if sess is not None and self._current_session_id is None:
            with self._lock:
                self._current_session_id = sess.id
            self._write_pointer(sess.id)
        return sess

    def switch(self, session_id: str) -> bool:
        sid = _safe_id(session_id)
        sess = self.get(sid)
        if sess is None:
            return False
        with self._lock:
            old = self._current_session_id
        if old and old != sid:
            self.flush(old)
        with self._lock:
            self._current_session_id = sid
        self._write_pointer(sid)
        return True

    def delete(self, session_id: str) -> bool:
        sid = _safe_id(session_id)
        existed = self.get(sid) is not None or os.path.isfile(self.yaml_path(sid))
        with self._lock:
            self._sessions.pop(sid, None)
            self._dirty.discard(sid)
            self._dirty_since.pop(sid, None)
            self._rounds.pop(sid, None)
            self._file_locks.pop(sid, None)
            was_current = self._current_session_id == sid
        for path in (
            self.yaml_path(sid), self.pkl_path(sid),
            self.yaml_path(sid) + ".tmp", self.pkl_path(sid) + ".tmp"
        ):
            try:
                os.unlink(path)
            except OSError:
                pass
        if was_current:
            remaining = [x["id"] for x in self.list() if x["id"] != sid]
            next_id = remaining[0] if remaining else None
            with self._lock:
                self._current_session_id = next_id
            if next_id:
                self._write_pointer(next_id)
            else:
                try:
                    os.unlink(self._pointer_path())
                except OSError:
                    pass
        return existed

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        source: str = "text",
    ) -> bool:
        """追加一条消息。内存立即生效；落盘按窗口合并，强制点见模块说明。"""
        sid = _safe_id(session_id)
        sess = self.get(sid)
        if sess is None:
            return False
        with self._lock:
            sess.messages.append({
                "role": str(role or "user"),
                "content": str(content or ""),
                "timestamp": time.time(),
                "source": str(source or "text"),
            })
            if len(sess.messages) > MAX_SESSION_MESSAGES:
                del sess.messages[:-MAX_SESSION_MESSAGES]
            sess.updated_at = time.time()
            self._dirty.add(sid)
            self._dirty_since.setdefault(sid, time.monotonic())
            due = (
                len(self._dirty_since) >= FLUSH_DIRTY_THRESHOLD
                or (time.monotonic() - self._dirty_since[sid]) >= FLUSH_INTERVAL
            )
            if due:
                snapshot = (self._meta(sess), list(sess.messages))
        if due:
            self._flush_one(sid, snapshot)
        return True

    def _flush_one(self, sid: str, snapshot: Tuple[Dict[str, Any], List[Dict]]) -> None:
        meta, messages = snapshot
        try:
            self._write_snapshot(sid, meta, messages)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[Session] 写入 {sid} 失败: {exc}")
            return
        with self._lock:
            self._dirty.discard(sid)
            self._dirty_since.pop(sid, None)

    def flush(self, session_id: Optional[str] = None) -> int:
        """强制落盘。指定 id 则该会话必写；不指定则写全部脏会话。"""
        with self._lock:
            ids = [_safe_id(session_id)] if session_id else list(self._dirty)
            snapshots = []
            for sid in ids:
                sess = self._sessions.get(sid)
                if sess is not None:
                    snapshots.append((sid, (self._meta(sess), list(sess.messages))))
        for sid, snap in snapshots:
            self._flush_one(sid, snap)
        return len(snapshots)

    def save_sync(self, sess: Session) -> bool:
        """chat.py 每轮收尾调用：接受 Session 对象，更新缓存并立即落盘。"""
        sid = _safe_id(getattr(sess, "id", ""))
        with self._lock:
            current = self._sessions.get(sid)
            if current is not None and current is not sess:
                current.messages = list(getattr(sess, "messages", []) or [])
                current.updated_at = float(getattr(sess, "updated_at", 0) or time.time())
                current.name = str(getattr(sess, "name", current.name) or current.name)
                current.character_id = str(
                    getattr(sess, "character_id", current.character_id) or ""
                )
                target = current
            else:
                target = sess
                self._sessions[sid] = sess
            snapshot = (self._meta(target), list(target.messages))
        self._flush_one(sid, snapshot)
        return True

    def _atexit_flush(self) -> None:
        try:
            self.flush()
        except Exception:  # noqa: BLE001 - 退出流程不允许再抛
            pass
