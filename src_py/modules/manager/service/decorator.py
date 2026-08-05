from functools import wraps
from typing import Generic, Optional, Type

from .manager import service_manager,T

class ServiceDecorator(Generic[T]):
    def __init__(self, id: Optional[str] = None) -> None:
        self.id = id or ""

    def __call__(self, cls: Type[T]) -> Type[T]:
        self.id = self.id or cls.__name__
        original_init = cls.__init__
        original_start = getattr(cls, "start", None)
        original_stop = getattr(cls, "stop", None)
        original_close = getattr(cls, "close", None)

        @wraps(original_init)
        def __init__(instance, *args, **kwargs):
            original_init(instance, *args, **kwargs)
            service_manager.register_service(self.id, instance)

        def start(instance, *args, **kwargs):
            return service_manager.start_service(self.id, *args, **kwargs)

        def stop(instance, *args, **kwargs):
            return service_manager.stop_service(self.id, *args, **kwargs)

        def close(instance, *args, **kwargs):
            return service_manager.close_service(self.id, *args, **kwargs)

        cls.__init__ = __init__  # type: ignore[method-assign]
        if original_start is not None:
            setattr(cls, "start_original", original_start)
            cls.start = start  # type: ignore[method-assign]
        if original_stop is not None:
            setattr(cls, "stop_original", original_stop)
            cls.stop = stop  # type: ignore[method-assign]
        if original_close is not None:
            setattr(cls, "close_original", original_close)
            cls.close = close  # type: ignore[method-assign]
        return cls


def Service(id: Optional[str] = None) -> Type[T]: # type: ignore
    return ServiceDecorator[T](id) # type: ignore[type-arg]
