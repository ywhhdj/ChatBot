from functools import wraps
from typing import Any, Callable, Optional,TypeVar
from .bus import event_bus
from .data import BaseEvent
from . import types

T = TypeVar("T", bound=object)

def on(event: str, callback: Callable[..., Any]):
    if event is None:
        raise ValueError("callback event 不能为空")
    event_bus.on(event, callback)
def off(event: str, callback: Optional[Callable] = None) -> None:
    event_bus.off(event, callback)
def emit(event: BaseEvent) -> Optional[Any]:
    if event.args:
        if event.kwargs:
            return event_bus.emit(event.type, *event.args, **event.kwargs)
        return event_bus.emit(event.type, *event.args)
    if event.kwargs:
        return event_bus.emit(event.type, **event.kwargs)
    return event_bus.emit(event.type)

def on_event(event_type: str):
    def wrapper(fn: Callable,*args: Any, **kwargs: Any):
        event_bus.on(event_type, fn)
        return fn(*args, **kwargs)
    return wrapper

def on_event_class(events: list[tuple[str, str]]):
    """
        事件类装饰器，用于注册事件处理方法
        Parameters:
            events: 事件类型和方法名的元组列表，每个元组包含事件类型和方法名，用于注册事件处理方法
    """
    def decorator(cls):
        # from ..config import get_config
        # config = get_config()
        # if config.debug:
        #     return cls
        def offEvent(self):
            for event_type, method_name in events:
                method = getattr(self, method_name, None)
                if method and callable(method):
                    event_bus.off(event_type, method)
        
        original_init = cls.__init__
        
        @wraps(original_init)
        def new_init(self, *args, **kwargs):
            # 先执行原始初始化
            original_init(self, *args, **kwargs)
            
            # 初始化完成后再注册事件
            for event_type, method_name in events:
                method = getattr(self, method_name)
                if not callable(method):
                    raise ValueError(f"方法 {method_name} 不是可调用的")
                event_bus.on(event_type, method)
        # 清理逻辑保持不变
        if hasattr(cls, "__del__"):
            original_del = cls.__del__
            @wraps(original_del)
            def new_del(self): # type: ignore[method-assignment]
                offEvent(self)
                if original_del:
                    original_del(self)
        else:
            def new_del(self):
                offEvent(self)
        
        cls.__init__ = new_init
        cls.__del__ = new_del
        return cls
    return decorator
