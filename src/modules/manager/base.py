"""manager 包内各管理器的公共基类。

README 的 `modules/manager/` 下有 `base.py`，但源码中缺失，而
`manager/dispatcher.py` 与 `manager/pipeline.py` 都在
`from .base import _BaseManager` —— 导入即 ImportError。

约定（两个子类都遵守）：

    def __init__(self):
        if self._initialized:      # 重复初始化保护
            return
        ...
        self._initialized = True

`_initialized` 必须是**类属性**默认 False：实例首次赋值前读到的
是类属性，这样"未初始化"判断在实例属性还不存在时也能成立。
"""

from __future__ import annotations

import threading
from typing import Any, Optional


class BaseManager:
    """管理器基类：初始化保护 + 可选锁 + 停止钩子。"""

    # 类级默认值：实例创建前即可读取
    _initialized: bool = False
    _lock: threading.RLock

    def __init__(self) -> None:
        # 子类通常会覆盖 __init__ 并在开头做 `if self._initialized: return`
        # 这里只在没有锁时补一个，避免子类各自重复创建。
        if not hasattr(self, "_lock"):
            self._lock = threading.RLock()
        self._initialized = True

    @property
    def is_initialized(self) -> bool:
        return bool(getattr(self, "_initialized", False))

    def mark_initialized(self) -> None:
        self._initialized = True

    def reset(self) -> None:
        """把实例恢复为未初始化状态（测试 / 重新配置时用）。"""
        self._initialized = False

    def stop(self) -> None:
        """停止钩子，子类按需覆盖。默认什么都不做。"""

    def close(self) -> None:
        self.stop()
