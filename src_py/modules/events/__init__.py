import weakref
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

from regex import R

from .. import runtime
from .data import BaseEvent
from . import types

T = TypeVar("T", bound=object)


def on(event: str, callback: Callable[..., Any]) -> None:
    if event is None:
        raise ValueError("callback event 不能为空")
    runtime.manager.event_bus.on(event, callback)  # type: ignore[union-attr]


def off(event: str, callback: Optional[Callable] = None) -> None:
    runtime.manager.event_bus.off(event, callback)  # type: ignore[union-attr]


def emit(event: BaseEvent) -> Optional[Any]:
    if event.args:
        if event.kwargs:
            return runtime.manager.event_bus.emit(event.type, *event.args, **event.kwargs)  # type: ignore[union-attr]
        return runtime.manager.event_bus.emit(event.type, *event.args)  # type: ignore[union-attr]
    if event.kwargs:
        return runtime.manager.event_bus.emit(event.type, **event.kwargs)  # type: ignore[union-attr]
    return runtime.manager.event_bus.emit(event.type)  # type: ignore[union-attr]


def on_event(event_type: str):
    def decorator(fn: Callable) -> Callable:
        runtime.manager.event_bus.on(event_type, fn)  # type: ignore[union-attr]
        return fn

    return decorator


def on_event_class(events: list[tuple[str, str]]):
    """类级事件注册装饰器。

    Parameters:
        events: [(事件类型, 方法名), ...]

    注册发生在每个实例 __init__ 之后，因此拿到的是 bound method。
    用 WeakMethod 注册，实例被回收后自动解绑，不需要依赖 __del__。
    """

    def decorator(cls):
        original_init = cls.__init__

        def unbind(self) -> None:
            for event_type, method_name in events:
                method = getattr(self, method_name, None)
                if method is not None and callable(method):
                    runtime.manager.event_bus.off(event_type, method)  # type: ignore[union-attr]

        @wraps(original_init)
        def new_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            for event_type, method_name in events:
                method = getattr(self, method_name, None)
                if not callable(method):
                    raise ValueError(f"方法 {method_name} 不是可调用的")
                # B12：弱引用注册，避免总线强持有实例
                if hasattr(method, "__self__"):
                    runtime.manager.event_bus.on(event_type, weakref.WeakMethod(method), weak=True)  # type: ignore[union-attr]
                else:
                    runtime.manager.event_bus.on(event_type, method)  # type: ignore[union-attr]

        # 保留显式解绑能力，但不依赖 __del__ 做清理（解释器退出时序不可靠）
        cls.unbind_events = unbind
        cls.__init__ = new_init
        return cls

    return decorator