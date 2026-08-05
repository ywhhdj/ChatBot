__version__ = "0.1.2"

from functools import wraps
from threading import Lock

#单例装饰器
def singleton(cls=None,*args, **kwargs):
    def wrapper(cls,*args, **kwargs):
        cls._lock = Lock()
        cls._instance = None
        cls._initialized = False

        original_init = cls.__init__
        @wraps(original_init)
        def __init__(self, *args, **kwargs):
            if self._instance:
                return
            self._instance = self
            original_init(self, *args, **kwargs)
            self._initialized = True

        def __new__(cls, *args, **kwargs):
            if not cls._instance:
                with cls._lock:
                    if not cls._instance:
                        cls._instance = super().__new__(cls)
            return cls._instance
        
        cls.__init__ = __init__
        cls.__new__ = __new__
    if cls:
        wrapper(cls,*args, **kwargs)
    return cls
    

__all__ = [
    "__version__"
]