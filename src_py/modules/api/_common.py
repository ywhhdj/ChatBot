"""Controller 公共工具。

三条硬约束（沿用前几轮修复的架构）
──────────────────────────────────
1. **Web 线程只做转发**。任何耗时操作（LLM 推理、模型加载、文件 IO）
   都要么交给任务调度器（自有 loop），要么走 `asyncio.to_thread` 的线程池。
2. **不阻塞 Web loop**。await 的一定是"等待事件唤醒"，不是 sleep 轮询。
3. **碰 Qt 的操作走主线程派发器**，绝不在 Web 线程直接操作 Qt 对象。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Optional

from ..logger import logger

# 默认超时：覆盖一轮完整对话；前端可自行设置更短的超时
DEFAULT_TIMEOUT = 600.0


def get_schedular():
    from .. import runtime
    return runtime.manager.task_manager


def schedular_running() -> bool:
    try:
        s = get_schedular()
    except Exception:
        return False
    try:
        return bool(s.is_runing)  # type: ignore[union-attr]
    except Exception:
        return False


async def run_in_scheduler(
    func: Callable,
    *args,
    timeout: float = DEFAULT_TIMEOUT,
    task_type: str = "async",
    **kwargs,
) -> Any:
    """把函数提交到任务调度器并等待结果。

    与直接在路由里 `await func()` 的差别：producer 跑在调度器 loop，
    Web loop 只等一个 `threading.Event` 唤醒 —— 推理期间其它 HTTP 请求
    仍然正常响应（对应 api文档.md 0.4）。
    """
    s = get_schedular()
    ref = s.submit(func, *args, task_type=task_type, timeout=timeout, **kwargs)  # type: ignore[union-attr]
    return await ref.wait_async(timeout=timeout)


async def to_thread(func: Callable, *args, **kwargs) -> Any:
    return await asyncio.to_thread(func, *args, **kwargs)


def now_ms(start: float) -> int:
    return int((time.time() - start) * 1000)


def safe_dict(value: Any) -> dict:
    """把任意对象转成可序列化 dict（pydantic / dataclass / 普通对象）。"""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    for attr in ("model_dump", "to_dict", "__dict__"):
        fn = getattr(value, attr, None)
        if fn is None:
            continue
        try:
            data = fn() if callable(fn) else fn
            if isinstance(data, dict):
                return data
        except Exception:
            continue
    return {}


def mask_secret(value: Any) -> Any:
    """敏感字段掩码：`sk-abcdefgh` -> `sk-***`。"""
    if not isinstance(value, str) or not value:
        return value
    lowered = value.lower()
    if any(k in lowered for k in ("key", "token", "secret", "password")):
        pass
    if len(value) <= 8:
        return "***"
    head = value[:3]
    return f"{head}-***" if not value.startswith("sk-") else "sk-***"


def mask_config(data: dict, keys: tuple[str, ...] = ("api_key", "token", "secret")) -> dict:
    out = dict(data)
    for k in list(out.keys()):
        if k in keys and isinstance(out[k], str) and out[k]:
            out[k] = mask_secret(out[k])
    return out


def state_name(state: Any) -> str:
    """ServiceState 可能是 enum 或字符串，统一成小写字符串。"""
    if state is None:
        return "stopped"
    value = getattr(state, "value", state)
    return str(value).lower()


def try_import(path: str, attr: str) -> Any:
    """安全地按 `a.b.c:attr` 取值，失败返回 None（依赖缺失不让整个 API 挂掉）。"""
    try:
        module = __import__(path, fromlist=[attr])
        return getattr(module, attr, None)
    except Exception as e:
        logger.debug(f"[API] import {path}.{attr} failed: {e}")
        return None