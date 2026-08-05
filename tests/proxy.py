from typing import Callable, Dict, Generic, Optional
from ...types import T,P,R

class TaskSchedularProxy(Generic[T, P, R]):
    def __init__(self):
        from ..src_py.modules.manager.task.schedular import get_task_schedular
        self.scheduler=get_task_schedular()
        self._wrapped_objects: Dict[str, T] = {}
        self._original_methods: Dict[str, Dict[str, Callable[P, R]]] = {}
    
    def start(self):
        if not self.scheduler.is_runing:
            self.scheduler.start()
    
    def stop(self):
        for object_id in self._wrapped_objects:
            self.remove_proxy(object_id)
    
    def remove_proxy(self, object_id: str) -> bool:
        if not self.scheduler.is_runing:
            return False
        """取消对象包装"""
        if object_id in self._wrapped_objects:
            obj = self._wrapped_objects[object_id]
            original_methods = self._original_methods.get(object_id, {})
            # 恢复原始方法
            for method_name, original_method in original_methods.items():
                setattr(obj, method_name, original_method)
            # 清理
            del self._wrapped_objects[object_id]
            del self._original_methods[object_id]
            return True
        return False

    def create_proxy(self, obj: T, object_id: Optional[str] = None,exclude_methods: Optional[list[str]] = None,include_methods: Optional[list[str]] = None) -> T:
        """
        包装对象的所有方法，使其通过调度器执行
        
        Args:
            obj: 要包装的对象
            object_id: 对象ID，不提供则自动生成
            
        Returns:
            包装后的对象
        """
        if object_id is None:
            object_id = f"obj_{len(self._wrapped_objects)}_{id(obj)}"
        
        # 保存原始对象
        self._wrapped_objects[object_id] = obj
        self._original_methods[object_id] = {}
        # 获取所有公共方法
        methods:list[str]=[]
        if exclude_methods is not None:
            exclude_methods=list(set(exclude_methods)|set(['__init__','__new__']))
        for name in dir(obj):
            if not name.startswith('_') and callable(getattr(obj, name)) and exclude_methods is not None and name not in exclude_methods:
                if include_methods:
                    if name in include_methods:
                        methods.append(name)
                else:
                    methods.append(name)
        # 包装每个方法
        for method_name in methods:
            original_method = getattr(obj, method_name)
            # 保存原始方法
            self._original_methods[object_id][method_name] = original_method
            # 创建包装方法
            # wrapped_method = scheduler(original_method)
            # # 替换原方法
            # setattr(obj, method_name, wrapped_method)
        print(f"📦 对象包装完成: {object_id} ({len(methods)} 个方法)")
        return obj

_task_task_proxy=None

def get_task_proxy():
    global _task_task_proxy
    if _task_task_proxy is None:
        _task_task_proxy = TaskSchedularProxy()
    return _task_task_proxy
