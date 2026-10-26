import time
from typing import Any, Callable, Iterable, Mapping, Optional
from uuid import uuid4
def get_device():
    device = "cpu"
    try:
        from torch import cuda
        device = ""
        if cuda.is_available():
            device = "cuda"
    except ImportError:
        pass
    return device

def create_daemon_thread(target: Callable[..., object], name: Optional[str] = None, args:Iterable[Any]=(), kwargs: Optional[Mapping[str, Any]] = None):
    from threading import Thread
    return Thread(target=target, name=name, args=args, kwargs=kwargs, daemon=True)

def id_generator(prefix: str = "",suffix: str = "") -> str:
    if prefix:
        prefix += "_"
    if suffix:
        suffix = f"_{suffix}"
    return prefix+f"{int(time.time())}_{uuid4().hex[:6]}"+suffix

#获取当前格式化时间
def format_time(format: str = "%Y-%m-%d %H:%M:%S", local_time: bool = True) -> str:
    return time.strftime(format, time.localtime() if local_time else time.gmtime())

def any_to_str(context: Any) -> str:
    if context is None:
        return ""
    if isinstance(context, str):
        return context
    if isinstance(context, dict):
        values: list[str] = []
        for value in context.values():
            if isinstance(value, (str, int, float, bool)):
                values.append(str(value))
        return " ".join(values)
    return str(context)