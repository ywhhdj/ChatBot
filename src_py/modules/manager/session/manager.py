"""会话存档管理。"""

from __future__ import annotations
import os
import threading
import time
from dataclasses import asdict
from typing import Any, Dict, Optional

from .models import RoundRecord, Session, SaveMetadata
from ...runtime import RuntimePath
from ...logger import logger
from ...utils.util import id_generator
from ...utils.file import pickle,yaml

# 单会话保留的最近消息条数
MAX_SESSION_MESSAGES = 200


class SessionManager:
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    _instance = None

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self.base_path = RuntimePath.get_user_data_path("saves")
        os.makedirs(self.base_path, exist_ok=True)
        self._sessions: Dict[str, Session] = {}
        self._current_session_id: Optional[str] = None
        self._lock = threading.RLock()
        self._file_locks: Dict[str, threading.Lock] = {}
        self._initialized = True

    def begin_round(
        self,
        user_input: str,
        character_id: str = "",
        route: str = "pure_chat",
        session_id: str = ""
    ) -> "RoundRecord":
        """一轮 = 用户发起 → 路由 → （轮内可能多轮次工具调用）→ 回复结束"""
        rec= RoundRecord(
            session_id=session_id or (self._current_session_id or ""),
            character_id=character_id or "",
            route=str(getattr(route, "value", route) or "pure_chat"),
            user_input=user_input,
            started_at=time.time(),
        )
        with self._lock:
            self._current_round = rec
        return rec

    def current_round(self) -> Optional[Any]:
        with self._lock:
            return getattr(self, "_current_round", None)

    def record_tool_call(self, item: Dict[str, Any]) -> None:
        """轮内记录一次工具调用。"""
        with self._lock:
            rec = getattr(self, "_current_round", None)
        if rec is None:
            return
        rec.tool_calls.append(dict(item or {}))

    def set_route(self, route: Any) -> None:
        with self._lock:
            rec = getattr(self, "_current_round", None)
        if rec is not None:
            rec.route = str(getattr(route, "value", route) or "")

    def end_round(self, reply: str = "") -> Optional[Any]:
        """结束当前轮，产出 RoundRecord"""
        with self._lock:
            rec = getattr(self, "_current_round", None)
            self._current_round = None
        if rec is None:
            return None
        rec.reply = reply
        rec.ended_at = time.time()
        return rec
    
    def create(
        self,
        name: str,
        character_id: str,
        session_id: Optional[str] = None,
    ) -> Session:
        sess = Session(
            id=session_id or id_generator("session_"),
            name=name,
            character_id=character_id,
            created_at=time.time(),
            updated_at=time.time(),
            messages=[],
            memory_ids=[],
            metadata=SaveMetadata(),
        )
        with self._lock:
            self._sessions[sess.id] = sess
        return sess
    
    def _file_lock(self, session_id: str) -> threading.Lock:
        with self._lock:
            lock = self._file_locks.get(session_id)
            if lock is None:
                lock = threading.Lock()
                self._file_locks[session_id] = lock
            return lock
    

    def yaml_path(self, session_id: str) -> str:
        return os.path.join(self.base_path, f"{session_id}.yaml")


    def pkl_path(self, session_id: str) -> str:
        return os.path.join(self.base_path, f"{session_id}.messages.pkl")
    
    def _write(self, sess: Session) -> None:
        with self._file_lock(sess.id):
            payload = asdict(sess)
            yaml_path = self.yaml_path(sess.id)
            tmp_path = f"{yaml_path}.tmp"
            try:
                yaml.write_yaml(tmp_path, payload)
                os.replace(tmp_path, yaml_path)
            except Exception as exc:
                logger.error(f"[Session] 写入 {yaml_path} 失败: {exc}")
                return

            pkl_path = self.pkl_path(sess.id)
            tmp_pkl = f"{pkl_path}.tmp"
            try:
                pickle.write_pickle(tmp_pkl,list(sess.messages))
                os.replace(tmp_pkl, pkl_path)
            except Exception as exc:
                logger.warning(f"[Session] 写入 {pkl_path} 失败: {exc}")