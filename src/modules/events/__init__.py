"""事件总线门面"""
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

from .. import runtime
from .data import BaseEvent
from . import types

T = TypeVar("T", bound=object)


def _bus(required: bool = True):
    """取事件总线；未初始化时不让 `runtime.manager is None` 漏到业务层。"""
    mgr = getattr(runtime, "manager", None)
    if mgr is None:
        mgr = runtime.instance()
    bus = getattr(mgr, "event_bus", None)
    if bus is None and required:
        raise RuntimeError("event bus not initialized")
    return bus


def on(event: str, callback: Callable[..., Any]) -> None:
    if event is None:
        raise ValueError("callback event 不能为空")
    _bus().on(event, callback) #type: ignore


def off(event: str, callback: Optional[Callable] = None) -> None:
    bus = _bus(required=False)
    if bus is not None:
        bus.off(event, callback)


def emit(event: BaseEvent) -> Optional[Any]:
    bus = _bus()
    if event.args:
        if event.kwargs:
            return bus.emit(event.type, *event.args, **event.kwargs) #type: ignore
        return bus.emit(event.type, *event.args) #type: ignore
    if event.kwargs:
        return bus.emit(event.type, **event.kwargs) #type: ignore
    return bus.emit(event.type) #type: ignore


def on_event(event_type: str):
    def decorator(fn: Callable) -> Callable:
        _bus().on(event_type, fn) #type: ignore
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
            bus = _bus(required=False)
            if bus is None:
                return
            for event_type, method_name in events:
                method = getattr(self, method_name, None)
                if method is not None and callable(method):
                    bus.off(event_type, method)

        @wraps(original_init)
        def new_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            bus = _bus()
            for event_type, method_name in events:
                method = getattr(self, method_name, None)
                if not callable(method):
                    raise ValueError(f"方法 {method_name} 不是可调用的")
                # 弱引用注册，避免总线强持有实例
                if hasattr(method, "__self__"):
                    bus.on(event_type, method, weak=True) #type: ignore
                else:
                    bus.on(event_type, method) #type: ignore

        # 保留显式解绑能力，但不依赖 __del__ 做清理（解释器退出时序不可靠）
        cls.unbind_events = unbind
        cls.__init__ = new_init
        return cls

    return decorator
