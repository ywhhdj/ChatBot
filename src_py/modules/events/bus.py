import asyncio
import inspect
from typing import Callable, Any, Optional, TypeVar, TypedDict, Dict,Generic,List
from collections import defaultdict
from threading import RLock
from inspect import iscoroutinefunction
import weakref

T = TypeVar("T", bound=object)


class LeakProofEventBus(Generic[T]):

    def __init__(self):
        # event_name -> [Listener, ...]
        self.__strong_listeners: Dict[str, List[Callable]] = defaultdict(list)
        self.__weak_listeners: Dict[str, List[weakref.ref]] = defaultdict(list)
        self.__lock = RLock()
    
    def on(self, event_type: str, callback: Callable, weak: bool = False):
        if weak:
            self.__weak_listeners[event_type].append(weakref.ref(callback))
        else:
            self.__strong_listeners[event_type].append(callback)

    def off(self, event_type: str, callback: Optional[Callable] = None):
        """取消注册"""
        # 强引用
        if event_type in self.__strong_listeners:
            for i, cb in enumerate(self.__strong_listeners[event_type]):
                if cb == callback:
                    del self.__strong_listeners[event_type][i]
                    break
            if not self.__strong_listeners[event_type]:
                del self.__strong_listeners[event_type]
        
        # 弱引用
        if event_type in self.__weak_listeners:
            for i, ref in enumerate(self.__weak_listeners[event_type]):
                if ref() == callback:
                    del self.__weak_listeners[event_type][i]
                    break
            if not self.__weak_listeners[event_type]:
                del self.__weak_listeners[event_type]

    def emit(self, event: str, *args, **kwargs) -> Optional[T]:
        results = []
        # 强引用
        for callback in self.__strong_listeners.get(event, []):
            try:
                if iscoroutinefunction(callback):
                    results.append(asyncio.run(callback(*args, **kwargs)))
                else:
                    results.append(callback(*args, **kwargs))
            except Exception as e:
                print(f"Event callback error: {e}")
        
        # 弱引用
        alive = []
        
        for ref in self.__weak_listeners.get(event, []):
            callback = ref()
            if callback is not None:
                alive.append(ref)
                try:
                    if iscoroutinefunction(callback):
                        results.append(asyncio.run(callback(*args, **kwargs)))
                    else:
                        results.append(callback(*args, **kwargs))
                except Exception as e:
                    print(f"Weak event callback error: {e}")
        if alive:
            self.__weak_listeners[event] = alive
        return results[-1] if results else None
    
    def clear(self) -> None:
        with self.__lock:
            self.__strong_listeners.clear()
            self.__weak_listeners.clear()
        
event_bus = LeakProofEventBus()
