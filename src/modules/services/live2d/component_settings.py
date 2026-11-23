"""Live2D **组件 UI 设置**的持久化（与 service config / 存档完全解耦）。

存放位置：``<user_data>/live2d/ui_settings.json``，只保存 107 个组件级键
（``settings.COMPONENT_KEYS``）；5 个对外字段（``settings.PUBLIC_KEYS``）
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from ...runtime import RuntimePath
from ...utils.file.atomic import atomic_write_json
from .settings import (
    COMPONENT_KEYS, DEFAULTS, PUBLIC_KEYS, _clone, normalize,
    split_component, split_public,
)

_FILE_NAME = "ui_settings.json"


class ComponentSettingsStore:
    """线程安全的组件设置读写。"""

    def __init__(self, path: Optional[Path | str] = None) -> None:
        if path is not None:
            self._path = Path(path)
        else:
            self._path = Path(RuntimePath.get_user_data_path("live2d")) / _FILE_NAME
        self._lock = threading.RLock()
        self._cache: Optional[Dict[str, Any]] = None

    @property
    def path(self) -> Path:
        return self._path

    @property
    def exists(self) -> bool:
        return self._path.is_file()

    # ── 读 ───────────────────────────────────────────────────────

    def _defaults_component(self) -> Dict[str, Any]:
        return {k: _clone(DEFAULTS[k]) for k in COMPONENT_KEYS}

    def _read_disk(self) -> Dict[str, Any]:
        if not self._path.is_file():
            return {}
        try:
            raw = json.loads(self._path.read_text("utf-8"))
            if not isinstance(raw, dict):
                return {}
            # 老版本文件可能混入对外 5 项 / 旧别名，这里一律过滤 + 归一化
            full = normalize(raw)
            return {k: full[k] for k in COMPONENT_KEYS}
        except (OSError, ValueError, TypeError):
            return {}

    def load(self) -> Dict[str, Any]:
        """返回完整的组件设置（107 项，含默认值），不含对外 5 项。"""
        with self._lock:
            if self._cache is None:
                merged = self._defaults_component()
                merged.update(self._read_disk())
                self._cache = merged
            return {k: _clone(v) for k, v in self._cache.items()}

    # ── 写 ───────────────────────────────────────────────────────

    def save(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        """保存组件设置；自动剔除对外 5 项，返回落盘后的组件配置。"""
        component = split_component(cfg)
        full = normalize({**self._defaults_component(), **component})
        payload = {k: full[k] for k in COMPONENT_KEYS}
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(str(self._path), payload)
            self._cache = dict(payload)
        return self.load()

    def patch(self, changes: Dict[str, Any]) -> Dict[str, Any]:
        """只改若干项，其余保留。"""
        with self._lock:
            current = self.load()
            current.update(split_component(changes))
            return self.save(current)

    def reset(self) -> Dict[str, Any]:
        """恢复组件默认设置。"""
        with self._lock:
            self._cache = self._defaults_component()
            self._path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(str(self._path), dict(self._cache))
            return self.load()

    def clear_cache(self) -> None:
        with self._lock:
            self._cache = None

    # ── 两层汇合 ─────────────────────────────────────────────────

    def merge(self, public_cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """组件设置打底 + 对外 5 项覆盖 → 完整 normalize 后的 cfg。

        ``public_cfg`` 可能来自 ``Live2DConfig.to_dict()``（含 service/name/
        enabled）或 ``on_config_change`` 的 new_config，只挑 5 个键。
        """
        public = split_public(public_cfg or {})
        raw: Dict[str, Any] = self.load()
        raw.update(public)
        return normalize(raw)

    def public_view(self, full_cfg: Dict[str, Any]) -> Dict[str, Any]:
        """从完整 cfg 里取出 5 个对外字段（给状态/自检用）。"""
        return split_public(full_cfg)

    def component_view(self, full_cfg: Dict[str, Any]) -> Dict[str, Any]:
        """从完整 cfg 里取出 107 个组件字段（给设置面板用）。"""
        return split_component(full_cfg)


def default_store() -> ComponentSettingsStore:
    return ComponentSettingsStore()


__all__ = ["ComponentSettingsStore", "default_store", "PUBLIC_KEYS", "COMPONENT_KEYS"]
