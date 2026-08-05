from abc import ABC, abstractmethod
from threading import Lock

class _BaseManager(ABC):
    _lock=Lock()
    _instance=None
    _initialized=False

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if not cls._instance:
                cls._instance=super().__new__(cls)
        return cls._instance

    @abstractmethod
    def stop(self) -> None:
        raise NotImplementedError("stop method must be implemented")
