from __future__ import annotations
import asyncio
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from datetime import datetime
import heapq
import time
from typing import Any, AsyncGenerator, Callable, Dict, Generic, Literal, Optional, TypeVar, TypedDict, Union
from threading import Lock, Event, Thread

from ...events import on_event_class, types as EventType
from ...utils import util
from . import reference
from ..base import _BaseManager
from ...logger import logger

class TaskPriority:
    LOW = 1
    NORMAL = 5
    HIGH = 10
    CRITICAL = 20

class TaskStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


T = TypeVar("T", bound=object)

@dataclass
class Task(Generic[T]):
    func: Callable
    completion_event: Union[Event, asyncio.Event]
    id: str = field(default_factory=lambda: util.id_generator("task_"))
    type: "TaskSchedular.TaskType" = "auto"
    args: tuple = ()
    kwargs: Dict[str, Any] = field(default_factory=dict)
    timeout: float = 10
    priority: int = TaskPriority.NORMAL
    metadata: Dict[str, Any] = field(default_factory=dict)

    result: Optional[T] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    status: str = TaskStatus.PENDING
    result_future: Optional[Union[Future[T], asyncio.Future[T]]] = None

@on_event_class([
    (EventType.AppEventType.TaskSchedularEventType.START, "start"),
    (EventType.AppEventType.TaskSchedularEventType.STOP, "stop")
])
class TaskSchedular(Generic[T], _BaseManager):
    class TaskSchedularInfo(TypedDict):
        total_submitted: int
        sync_submitted: int
        async_submitted: int
        running: int
        completed: int
        failed: int
        canceled: int
        queue_size: int

    TaskType = Literal["auto", "sync", "async", "async_stream"]

    class TaskStatusInfo(TypedDict):
        task_id: str
        status: str
        task_type: TaskSchedular.TaskType
        completed_at: Optional[str]
        error: Optional[str]

    # ── 初始化 ──────────────────────────────────────────────
    def __init__(
        self,
        max_sync_workers: int = 30,
        max_async_workers: int = 20,
        max_streaming_workers: int = 20,
        sync_queue_size: int = 1000,
        async_queue_size: int = 1000,
        older_than_hours: float = 0.5
    ) -> None:
        if self._initialized:
            return
        
        self._instance = self

        self.max_sync_workers = max_sync_workers
        self.max_async_workers = max_async_workers
        self.sync_queue_size = sync_queue_size
        self.async_queue_size = async_queue_size
        self.max_streaming_workers = max_streaming_workers
        self.older_than_hours = older_than_hours

        self.is_runing = False

        self.status: TaskSchedular.TaskSchedularInfo = {
            "total_submitted": 0,
            "sync_submitted": 0,
            "async_submitted": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "canceled": 0,
            "queue_size": 0,
        }

        # ── 数据结构 ──
        self.__streaming_tasks: Dict[str, reference.TaskStreamingReference[T]] = {}
        self.__streaming_semaphore: Optional[asyncio.Semaphore] = None
        self.tasks: Dict[str, Task] = {}
        self.__sync_queue: list[tuple[int, float, str]] = []
        self.__async_queue: list[tuple[int, float, str]] = []

        # ★★★ 核心修复：合并为单把锁 ★★★
        # 原始代码有 __queue_lock + __task_lock 两把锁，
        # submit 和 dispatcher 以相反顺序获取 → AB-BA 死锁
        # 现在所有共享状态用同一把锁保护，根本不存在锁序问题
        self.__lock = Lock()

        self.__loop: Optional[asyncio.AbstractEventLoop] = None
        self.__semaphore: Optional[asyncio.Semaphore] = None

        self.__async_thred: Optional[Thread] = None
        self.__sync_thred: Optional[Thread] = None
        self.__cleaner_thread: Optional[Thread] = None
        self.__event_loop_thread: Optional[Thread] = None

        self.__sync_executor = ThreadPoolExecutor(max_workers=max_sync_workers)
        self._initialized = True

    def __init_async_loop(self):
        """初始化后台 asyncio 事件循环"""
        if self.__loop is not None and self.__loop.is_running():
            return

        with self.__lock:
            if self.__loop is not None and self.__loop.is_running():
                return

            def run_async_loop():
                loop = None
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    self.__streaming_semaphore = asyncio.Semaphore(self.max_streaming_workers)
                    self.__semaphore = asyncio.Semaphore(self.max_async_workers)
                    self.__loop = loop
                    logger.info("[TaskSchedular] Async event loop started")
                    self.__loop.run_forever()
                except Exception as e:
                    logger.error(f"[TaskSchedular] Async loop error: {e}")
                finally:
                    if loop and not loop.is_closed():
                        tasks = asyncio.all_tasks(loop)
                        for t in tasks:
                            t.cancel()
                        if tasks:
                            try:
                                loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
                            except:
                                pass
                        loop.close()
                    asyncio.set_event_loop(None)
                    self.__loop = None
                    self.__semaphore = None
                    self.__streaming_semaphore = None

            self.__event_loop_thread = util.create_daemon_thread(
                run_async_loop, name="AsyncEvent"
            )
            self.__event_loop_thread.start()

            # 等待事件循环就绪
            for _ in range(50):
                if self.__loop is not None and self.__loop.is_running():
                    return
                time.sleep(0.1)
            raise RuntimeError("AsyncEvent init error")

    def start(self):
        if self.is_runing:
            return
        self.is_runing = True
        self.__init_async_loop()

        self.__sync_thred = util.create_daemon_thread(
            self.__run_sync_dispatcher, name="SyncDispatcher"
        )
        self.__async_thred = util.create_daemon_thread(
            self.__run_async_dispatcher, name="AsyncDispatcher"
        )
        self.__cleaner_thread = util.create_daemon_thread(
            self.__clear_completed_tasks, name="TaskCleaner"
        )

        for t in [self.__sync_thred, self.__async_thred, self.__cleaner_thread]:
            if t is not None:
                t.start()

        TaskSchedular._init = True
        logger.info("[TaskSchedular] ✅ 调度器已启动")

    def stop(self, timeout: float = 5.0, wait: bool = True) -> None:
        if not self.is_runing:
            return
        self.is_runing = False

        if self.__loop is not None and self.__loop.is_running():
            try:
                self.__loop.call_soon_threadsafe(self.__loop.stop)
            except:
                pass

        thread_names = [
            (self.__sync_thred, "同步分发器"),
            (self.__async_thred, "异步分发器"),
            (self.__cleaner_thread, "任务清理器"),
            (self.__event_loop_thread, "事件循环线程"),
        ]
        for thread, name in thread_names:
            if thread and thread.is_alive():
                thread.join(timeout=timeout)
                if thread.is_alive():
                    logger.warning(f"[TaskSchedular] {name} 未能在 {timeout}s 内停止")
        try:
            self.__sync_executor.shutdown(wait=wait)
        except:
            pass

        with self.__lock:
            self.tasks.clear()
            self.__streaming_tasks.clear()
            self.__sync_queue.clear()
            self.__async_queue.clear()
            # 重置状态
            for key in ["running", "queue_size", "total_submitted",
                        "sync_submitted", "async_submitted",
                        "completed", "failed", "canceled"]:
                self.status[key] = 0

        logger.info("[TaskSchedular] 🛑 调度器已停止")

    async def submit_stream(
        self,
        async_gen_func: Callable[..., AsyncGenerator],
        timeout: float = 10,
        auto_close: bool = True,
        *args, **kwargs
    ) -> reference.TaskStreamingReference[T]:
        if self.__streaming_semaphore is None:
            raise RuntimeError("AsyncEvent not init")
        if self.__detect_task_type(async_gen_func) != "async_stream":
            raise TypeError(f"函数 {async_gen_func.__name__} 不是异步生成器")
        if self.__loop is None or not self.__loop.is_running():
            raise RuntimeError("AsyncEvent not init")

        async with self.__streaming_semaphore:
            stream_id = util.id_generator("stream_")
            stream = reference.TaskStreamingReference(
                task_id=stream_id, timeout=timeout, auto_close=auto_close
            )

            with self.__lock:
                self.__streaming_tasks[stream_id] = stream
                self.status["total_submitted"] += 1
                self.status["running"] += 1

            async def producer_task():
                try:
                    await stream.produce(async_gen_func(*args, **kwargs))
                except asyncio.CancelledError:
                    raise
                except Exception:
                    with self.__lock:
                        self.status["failed"] += 1
                    raise
                finally:
                    with self.__lock:
                        if stream.streaming_status != "stop":
                            self.status["running"] -= 1
                            self.status["completed"] += 1
                        self.__streaming_tasks.pop(stream_id, None)
            # future = asyncio.run_coroutine_threadsafe(
            #     producer_task(), 
            #     self.__loop
            # )
            stream.producer_task = asyncio.create_task(
                producer_task(), name=f"StreamProducer-{stream_id}"
            )

            def on_producer_done(_):
                if stream.streaming_task.auto_close:
                    asyncio.create_task(stream.close())
            # future.add_done_callback(on_producer_done)


            stream.producer_task.add_done_callback(on_producer_done)
            logger.info(f"[TaskSchedular] 🌊 提交流式任务: {stream_id}")
            return stream

    def submit(
        self,
        func: Callable,
        task_type: "TaskType" = "auto",
        timeout: float = 10,
        priority: int = TaskPriority.NORMAL,
        *args,
        **kwargs
    ) -> reference.TaskReference[T]:
        """
        提交任务 — 修复版

        原始问题：先获取 __queue_lock，再获取 __task_lock
        与 dispatcher 的锁序相反 → AB-BA 死锁

        修复：单把锁 __lock 保护所有操作，原子完成
        """
        if task_type == "auto":
            task_type = self.__detect_task_type(func)
        if task_type == "async_stream":
            raise TypeError("函数不能是异步生成器，请使用 submit_stream 提交流式任务")

        if task_type == "async":
            completion_event: Union[Event, asyncio.Event] = asyncio.Event()
        else:
            completion_event = Event()

        task = Task(
            func=func,
            args=args,
            kwargs=kwargs,
            type=task_type,
            timeout=timeout,
            priority=priority,
            completion_event=completion_event,
        )

        # ★ 单把锁，原子操作：注册任务 + 入队 + 更新状态 ★
        with self.__lock:
            self.tasks[task.id] = task

            item = (-task.priority, time.time(), task.id)
            if task.type == "async":
                heapq.heappush(self.__async_queue, item)
            else:
                heapq.heappush(self.__sync_queue, item)

            self.status["total_submitted"] += 1
            self.status["async_submitted"] += (task.type == "async")
            self.status["sync_submitted"] += (task.type == "sync")
            self.status["queue_size"] = len(self.__sync_queue) + len(self.__async_queue)

        logger.debug(f"[TaskSchedular] submit ✅ task_id={task.id} type={task.type}")
        print(f"[TaskSchedular] ✅ 提交任务: {self.__async_queue.__len__()}")
        return reference.TaskReference(task_id=task.id, _schedular=self)

    def get_stats(self) -> TaskSchedularInfo:
        with self.__lock:
            stats = self.status.copy()
            stats["queue_size"] = len(self.__sync_queue) + len(self.__async_queue)
            stats["running"] = sum(
                1 for t in self.tasks.values() if t.status == TaskStatus.RUNNING
            )
            return stats

    def get_task_status(self, task_id: str) -> Optional[TaskStatusInfo]:
        with self.__lock:
            task = self.tasks.get(task_id)
            if not task:
                return None
            return TaskSchedular.TaskStatusInfo(
                task_id=task.id,
                status=task.status,
                task_type=task.type,
                completed_at=task.completed_at.strftime("%Y-%m-%d %H:%M:%S") if task.completed_at else None,
                error=task.error,
            )

    async def wait_for_task_sync(self, task_id: str, timeout: Optional[float] = None) -> Optional[T]:
        # 先获取任务引用（不持锁等待）
        with self.__lock:
            task = self.tasks.get(task_id)
            if not task:
                raise ValueError(f"任务不存在: {task_id}")
            if task.status == TaskStatus.COMPLETED:
                return task.result
            elif task.status == TaskStatus.FAILED:
                raise Exception(f"任务执行失败: {task.error}")
            elif task.status == TaskStatus.CANCELLED:
                raise Exception(f"任务被取消: {task_id}")

        if isinstance(task.completion_event, asyncio.Event): # type: ignore
            await task.completion_event.wait()
        else:
            if not task.completion_event.wait(timeout=timeout):
                raise TimeoutError(f"等待任务结果超时: {timeout}s")

        with self.__lock:
            if task.status == TaskStatus.COMPLETED:
                return task.result
            elif task.status == TaskStatus.FAILED:
                raise Exception(f"任务执行失败: {task.error}")
            elif task.status == TaskStatus.CANCELLED:
                raise Exception(f"任务被取消: {task_id}")
        return None

    async def submit_and_wait_async(
        self,
        func: Callable,
        task_type: "TaskType" = "async",
        timeout: float = 10,
        priority: int = TaskPriority.NORMAL,
        *args, **kwargs
    ) -> Optional[T]:
        task_ref = self.submit(func, task_type, timeout, priority, *args, **kwargs)
        return await self.get_task_result_async(task_ref.task_id, timeout)

    async def get_task_result_async(self, task_id: str, timeout: Optional[float] = None) -> Optional[T]:
        with self.__lock:
            task = self.tasks.get(task_id)
            if not task:
                raise ValueError(f"任务不存在: {task_id}")

        if task.status == TaskStatus.COMPLETED:
            return task.result
        elif task.status == TaskStatus.FAILED:
            raise Exception(f"任务执行失败: {task.error}")
        elif task.status == TaskStatus.CANCELLED:
            raise asyncio.CancelledError(f"任务被取消: {task_id}")

        start = time.time()
        while True:
            if task.completion_event.is_set():
                with self.__lock:
                    if task.status == TaskStatus.COMPLETED:
                        return task.result
                    elif task.status == TaskStatus.FAILED:
                        raise Exception(f"任务执行失败: {task.error}")
                    elif task.status == TaskStatus.CANCELLED:
                        raise asyncio.CancelledError(f"任务被取消: {task_id}")

            if timeout and (time.time() - start) > timeout:
                raise asyncio.TimeoutError(f"等待任务结果超时: {timeout}s")

            await asyncio.sleep(0.05)

    def cancel_task(self, task_id: str) -> bool:
        with self.__lock:
            task = self.tasks.get(task_id)
            if not task or task.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
                return False

            task.status = TaskStatus.CANCELLED
            self.status["canceled"] += 1
            task.completion_event.set()

            # 从队列中移除
            for queue, key in [
                (self.__async_queue, "async_submitted"),
                (self.__sync_queue, "sync_submitted"),
            ]:
                for i, (_, _, tid) in enumerate(queue):
                    if tid == task_id:
                        queue.pop(i)
                        heapq.heapify(queue)
                        self.status[key] = max(0, self.status[key] - 1)
                        self.status["queue_size"] = max(0, self.status["queue_size"] - 1)
                        break

            # 取消 future
            if task.result_future and not task.result_future.done():
                task.result_future.cancel()

        return True

    # ── 类型检测 ────────────────────────────────────────────
    def __detect_task_type(self, func: Callable) -> TaskType:
        from inspect import isasyncgenfunction, iscoroutinefunction
        if isasyncgenfunction(func):
            return "async_stream"
        elif iscoroutinefunction(func):
            return "async"
        return "sync"

    # ── ★核心修复★ Sync Dispatcher ────────────────────────
    def __run_sync_dispatcher(self):
        while self.is_runing:
            print("[DEBUG] SyncDispatcher waiting for task...")
            task_to_run = None
            try:
                # ★ 加锁 → 弹出最高优先级任务 → 立即释放锁 ★
                with self.__lock:
                    if self.__sync_queue:
                        _, _, task_id = heapq.heappop(self.__sync_queue)
                        task_to_run = self.tasks.get(task_id)

                if task_to_run is None:
                    time.sleep(0.05)  # 队列空，短暂休眠
                    continue

                # ★ 锁外执行：不阻塞其他线程的 submit/get_stats/cancel ★
                if task_to_run.status == TaskStatus.PENDING:
                    self.__execute_sync_task(task_to_run)

            except InterruptedError:
                logger.debug("[SyncDispatcher] 被中断")
                continue
            except Exception as e:
                logger.exception(f"[SyncDispatcher] 异常: {e}", exc_info=True)
                time.sleep(0.1)

        logger.info("[SyncDispatcher] 🛑 已停止")

    def __run_async_dispatcher(self):
        while self.is_runing:
            task_to_run = None
            try:
                with self.__lock:
                    if self.__async_queue:
                        _, _, task_id = heapq.heappop(self.__async_queue)
                        task_to_run = self.tasks.get(task_id)

                if task_to_run is None:
                    time.sleep(0.05)
                    continue

                if task_to_run.status == TaskStatus.PENDING:
                    if self.__loop and not self.__loop.is_closed():
                        asyncio.run_coroutine_threadsafe(
                            self.__execute_async_task(task_to_run), self.__loop
                        )

            except Exception as e:
                logger.exception(f"[AsyncDispatcher] 异常: {e}", exc_info=True)
                time.sleep(1)

        logger.info("[AsyncDispatcher] 🛑 已停止")

    def __execute_sync_task(self, task: Task):
        """执行同步任务"""
        # 加锁更新状态
        with self.__lock:
            if task.id not in self.tasks or task.status != TaskStatus.PENDING:
                return
            task.status = TaskStatus.RUNNING
            self.status["running"] += 1

        try:
            future = self.__sync_executor.submit(
                self.__wrap_sync_task, task.func, task.args, task.kwargs, task.id
            )
            # 回写 future 引用（需要加锁）
            with self.__lock:
                task.result_future = future
            # 注册回调（回调内部会加锁，安全）
            future.add_done_callback(lambda f: self.__handle_sync_task_result(f, task.id))
        except Exception as e:
            self.__mark_task_failed(task, str(e))

    def __wrap_sync_task(self, func, args, kwargs, task_id: str):
        try:
            return func(*args, **kwargs)
        except Exception:
            logger.exception(f"[TaskSchedular] 任务{task_id} 执行异常", exc_info=True)
            raise

    async def __execute_async_task(self, task: Task):
        """执行异步任务"""
        with self.__lock:
            if task.id not in self.tasks or task.status != TaskStatus.PENDING:
                return
            task.status = TaskStatus.RUNNING
            self.status["running"] += 1
        if self.__semaphore is None:
            self.__mark_task_failed(task, "AsyncEvent not init")
            return
        try:
            async with self.__semaphore:
                result = await task.func(*task.args, **task.kwargs)

            with self.__lock:
                task.result = result
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now()
                self.status["completed"] += 1
                self.status["running"] -= 1
                task.completion_event.set()

        except asyncio.CancelledError:
            with self.__lock:
                task.status = TaskStatus.CANCELLED
                self.status["canceled"] += 1
                self.status["running"] -= 1
                task.completion_event.set()
            raise
        except Exception as e:
            self.__mark_task_failed(task, str(e))

    def __mark_task_failed(self, task: Task, error: str):
        with self.__lock:
            task.error = error
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.now()
            self.status["failed"] += 1
            self.status["running"] -= 1
            task.completion_event.set()

    def __handle_sync_task_result(self, future: Future, task_id: str):
        with self.__lock:
            task = self.tasks.get(task_id)
            if not task:
                return
            task.completed_at = datetime.now()
            try:
                task.result = future.result()
                task.status = TaskStatus.COMPLETED
                self.status["completed"] += 1
            except Exception as e:
                task.error = str(e)
                task.status = TaskStatus.FAILED
                self.status["failed"] += 1
            finally:
                self.status["running"] -= 1
                task.completion_event.set()

    def __clear_completed_tasks(self):
        threshold = min(300, self.older_than_hours * 3600)
        logger.info(f"[TaskCleaner] 🧹 启动 (threshold={self.older_than_hours}h)")

        while self.is_runing:
            try:
                now = datetime.now()
                to_remove = []
                with self.__lock:
                    if not self.tasks:
                        time.sleep(threshold)
                        continue
                    for tid, task in list(self.tasks.items()):
                        if task.completed_at:
                            age = (now - task.completed_at).total_seconds()
                            if age > threshold:
                                to_remove.append(tid)
                    for tid in to_remove:
                        self.tasks.pop(tid, None)

                if to_remove:
                    logger.info(f"[TaskCleaner] 🧹 清理了 {len(to_remove)} 个已完成任务")
                time.sleep(threshold)
            except Exception as e:
                logger.error(f"[TaskCleaner] 异常: {e}")
                time.sleep(60)

    def set_older_than_hours(self, hours: float) -> None:
        self.older_than_hours = hours

schedular = TaskSchedular()