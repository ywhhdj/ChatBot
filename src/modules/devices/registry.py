"""设备角色登记表

`register` 帧是权威的 uid / device 来源；`device.hello` 只是旧客户端的兼容入口，
因此这里同时保存 role 与 register 附带的 uid，供未注册或半注册连接兜底。
所有索引都有界：断连必须 `unregister()`，否则会随重连无限增长。
"""

from __future__ import annotations

import threading
from typing import Dict, Optional, Set

VALID_ROLES = frozenset({"mobile", "desktop", "unknown"})
MAX_TRACKED = 256

_lock = threading.RLock()
_roles: Dict[str, str] = {}
_uids: Dict[str, str] = {}
_by_role: Dict[str, Set[str]] = {
    "mobile": set(), "desktop": set(), "unknown": set(),
}


def normalize_role(value: object) -> str:
    role = str(value or "unknown").strip().lower()
    return role if role in VALID_ROLES else "unknown"


def set_role(client_id: str, role: str, uid: str = "") -> None:
    """登记/更新一个连接的角色。重复调用只做差量移动，不产生重复集合项。"""
    if not client_id:
        return
    next_role = normalize_role(role)
    with _lock:
        old_role = _roles.get(client_id)
        if old_role == next_role and _uids.get(client_id, "") == uid:
            return
        if len(_roles) >= MAX_TRACKED and client_id not in _roles:
            # 有界：淘汰最早登记且已无活跃意义的连接（由 manager 侧先 disconnect）
            victim = next(iter(_roles))
            _forget(victim)
        if old_role is not None and old_role != next_role:
            _by_role.get(old_role, set()).discard(client_id)
        _roles[client_id] = next_role
        _uids[client_id] = uid
        _by_role.setdefault(next_role, set()).add(client_id)


def role_of(client_id: str) -> str:
    with _lock:
        return _roles.get(client_id, "unknown")


def uid_of(client_id: str) -> str:
    with _lock:
        return _uids.get(client_id, "")


def unregister(client_id: str) -> None:
    with _lock:
        _forget(client_id)


def _forget(client_id: str) -> None:
    role = _roles.pop(client_id, None)
    _uids.pop(client_id, None)
    if role is not None:
        _by_role.get(role, set()).discard(client_id)


def clear() -> None:
    with _lock:
        _roles.clear()
        _uids.clear()
        for bucket in _by_role.values():
            bucket.clear()


def targets(
    active: Dict[str, object],
    role: str,
    primary_only: bool = False,
    manager: Optional[object] = None,
    source_client_id: str = "",
) -> list:
    """按「同 uid 的 device 索引」优先找目标，回退到全局角色表。

    Args:
        active: manager.active_connections（只读快照语义）
        role: 目标角色 mobile / desktop
        primary_only: 只取主连接（避免多桌面同时演出）
        manager: WebSocketClientManager，用于 uid 维度定向
        source_client_id: 发起方，永远排除（U07 不回灌自己）
    """
    wanted = normalize_role(role)
    exclude = source_client_id

    if manager is not None:
        uid = ""
        try:
            uid = manager.uid_of(source_client_id)
        except Exception:
            uid = uid_of(source_client_id)
        if uid:
            try:
                hit = manager.device_targets(
                    uid, wanted, primary_only=primary_only, exclude=exclude
                )
            except Exception:
                hit = []
            if hit:
                return hit

    with _lock:
        candidates = [
            cid for cid in _by_role.get(wanted, set())
            if cid in active and cid != exclude
        ]

    # 只 register 未 hello 的桌面端：按 conn_info.device 兜底
    if not candidates and manager is not None:
        try:
            uid = manager.uid_of(source_client_id)
            for cid, info in list(manager.conn_info.items()):
                if cid == exclude or cid not in active:
                    continue
                if getattr(info, "device", "unknown") != wanted:
                    continue
                if uid and getattr(info, "uid", "") != uid:
                    continue
                candidates.append(cid)
        except Exception:
            pass

    if primary_only:
        return candidates[:1]
    return candidates


class _RoleRegistryFacade:
    """模块级门面，保持 `from .....devices import role_registry` 的写法可用。"""

    set_role = staticmethod(set_role)
    role_of = staticmethod(role_of)
    uid_of = staticmethod(uid_of)
    unregister = staticmethod(unregister)
    clear = staticmethod(clear)
    targets = staticmethod(targets)
    normalize_role = staticmethod(normalize_role)


role_registry = _RoleRegistryFacade()
