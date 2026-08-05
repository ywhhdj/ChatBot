import asyncio
import threading
from concurrent import futures
from ..logger import logger
from ..events import on_event_class,types
from .base import _BaseManager

@on_event_class([
    (types.AppEventType.MainThreadDispatcherEventType.RUN_ON_MAIN_THREAD,"run_on_main_thread"),
    (types.AppEventType.MainThreadDispatcherEventType.RUN_ASYNC_ON_MAIN_THREAD,"run_async_on_main_thread"),
    (types.AppEventType.MainThreadDispatcherEventType.STOP,"stop")
])
class MainThreadDispatcher(_BaseManager):
    
    def __init__(self):
        if self._initialized:
            return
        self._sync_tasks = [] 
        self._tasks_lock = threading.Lock()
        self._running = False
        self._ready = False
        self._main_loop = None
        self._pending_futures = {}
        self._future_counter = 0
        self._future_lock = threading.Lock()
        
        self._initialized = True
        logger.info("MainThreadDispatcher initialized")
    
    async def setup(self):
        if self._ready:
            return
        self._main_loop = asyncio.get_event_loop()
        self._ready = True
        self._running = True
        logger.info("MainThreadDispatcher setup complete")
    
    async def start_processing(self):
        if not self._ready:
            await self.setup()
        logger.info("MainThreadDispatcher processor started")
    
    def _process_pending_qt_tasks(self):
        tasks_to_execute = []
        
        with self._tasks_lock:
            if self._sync_tasks:
                tasks_to_execute = self._sync_tasks.copy()
                self._sync_tasks.clear()
        if tasks_to_execute:
            for task_data in tasks_to_execute:
                try:
                    func, args, kwargs, future_id = task_data
                    result = func(*args, **kwargs)
                    
                    # 通知等待的 Future
                    with self._future_lock:
                        if future_id in self._pending_futures:
                            self._pending_futures[future_id].set_result(result)
                            
                except Exception as e:
                    with self._future_lock:
                        if future_id in self._pending_futures:
                            self._pending_futures[future_id].set_exception(e)
    
    def run_on_main_thread(self, func, *args, **kwargs):
        """
        在主线程执行函数 - 从任何线程调用
        返回函数的执行结果
        """
        if not self._ready:
            raise RuntimeError("MainThreadDispatcher is not ready yet")
        
        # 检查是否已经在主线程
        if threading.current_thread() is threading.main_thread():
            return func(*args, **kwargs)
        
        # 创建 concurrent.futures.Future 用于跨线程通信
        with self._future_lock:
            future_id = self._future_counter
            self._future_counter += 1
            future = futures.Future()
            self._pending_futures[future_id] = future
        
        # 将任务添加到同步任务列表
        task_data = (func, args, kwargs, future_id)
        with self._tasks_lock:
            self._sync_tasks.append(task_data)
        
        # 唤醒 asyncio 事件循环，让它有机会处理其他事情
        if self._main_loop and self._main_loop.is_running():
            self._main_loop.call_soon_threadsafe(lambda: None)
        
        # 等待结果（阻塞当前线程）
        try:
            return future.result(timeout=5)
        except futures.TimeoutError:
            raise TimeoutError("Main thread task timed out")
        except Exception as e:
            logger.error(f"run_on_main_thread error: {e}")
            raise
    
    async def run_async_on_main_thread(self, coro_or_func, *args, **kwargs):
        """
        在主线程执行异步函数 - 从 asyncio 线程调用
        """
        if not self._ready:
            raise RuntimeError("MainThreadDispatcher is not ready yet")
        
        # 检查是否已经在主线程
        if threading.current_thread() is threading.main_thread():
            if asyncio.iscoroutine(coro_or_func):
                return await coro_or_func
            elif asyncio.iscoroutinefunction(coro_or_func):
                return await coro_or_func(*args, **kwargs)
            else:
                return coro_or_func(*args, **kwargs)
        
        # 对于异步函数，我们需要包装成同步函数在 Qt 线程执行
        # 然后通过 asyncio.wrap_future 等待结果
        
        with self._future_lock:
            future_id = self._future_counter
            self._future_counter += 1
            future = futures.Future()
            self._pending_futures[future_id] = future
        
        if asyncio.iscoroutine(coro_or_func):
            # 协程不能在 Qt 线程直接运行，需要用新的事件循环
            def sync_wrapper(): # type: ignore
                new_loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(new_loop)
                    return new_loop.run_until_complete(coro_or_func)
                finally:
                    new_loop.close()
            
            task_data = (sync_wrapper, (), {}, future_id)
        elif asyncio.iscoroutinefunction(coro_or_func):
            def sync_wrapper():
                new_loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(new_loop)
                    return new_loop.run_until_complete(coro_or_func(*args, **kwargs))
                finally:
                    new_loop.close()
            
            task_data = (sync_wrapper, (), {}, future_id)
        else:
            task_data = (coro_or_func, args, kwargs, future_id)
        
        with self._tasks_lock:
            self._sync_tasks.append(task_data)
        
        # 等待结果
        try:
            return await asyncio.wrap_future(future)
        except asyncio.TimeoutError:
            raise TimeoutError("Async main thread task timed out")
    
    def stop(self):
        self._running = False
        self._ready = False
        
        with self._future_lock:
            for future_id, future in self._pending_futures.items():
                if not future.done():
                    future.cancel()
            self._pending_futures.clear()
        
        with self._tasks_lock:
            self._sync_tasks.clear()

main_thread_dispatcher = None
def get_main_thread_dispatcher():
    global main_thread_dispatcher
    if main_thread_dispatcher is None:
        main_thread_dispatcher = MainThreadDispatcher()
    return main_thread_dispatcher