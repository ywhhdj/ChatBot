from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
import time
from typing import Any, AsyncGenerator, Callable, Generic, Literal, Optional, TypeVar, TypedDict
from ...utils import util
from inspect import iscoroutinefunction
T = TypeVar("T", bound=object)

class TaskStreamingReference(Generic[T]):
    """
    任务流式结果容器
    - 支持异步迭代获取结果
    - 支持超时
    """
    @dataclass
    class StreamingTask:
        id:str=field(default_factory=lambda: util.id_generator("stream_"))
        timeout:float=10
        auto_close:bool=True
    
    class StreamingTaskStatus(TypedDict):
        start_time:Optional[float]
        end_time:Optional[float]
        duration:float
        errors:int
        is_running:bool
    
    StreamTaskStatus=Literal["running","reset","paused","stop"]
    
    def __init__(self, task_id: str="",timeout:float=10,auto_close:bool=True):
        self.streaming_task = TaskStreamingReference.StreamingTask(id=task_id,timeout=timeout,auto_close=auto_close)
        
        self.timeout = timeout
        self.auto_close = auto_close
        # 流控制
        self.__producer_done = asyncio.Event()
        self.__consumer_ready = asyncio.Event()
        self.__producer_exception: Optional[Exception] = None
        
        # 通信通道
        self.__data_event = asyncio.Event()
        self.__data_value: Optional[T] = None
        self.__control_event = asyncio.Event()

        self.__is_started = False
        self.__is_closed = False
        self.producer_task: Optional[asyncio.Task] = None
        self.consumer_task: Optional[asyncio.Task] = None
        self.__control_signal: TaskStreamingReference.StreamTaskStatus = "running"
        
        # 统计
        self._stats: TaskStreamingReference.StreamingTaskStatus = {
            "start_time": None,
            "end_time": None,
            "duration": 0,
            "errors": 0,
            "is_running": False
        }
    
    @property
    def task_id(self)->str:
        return self.streaming_task.id
    
    @property
    def streaming_status(self)->TaskStreamingReference.StreamTaskStatus:
        return self.__control_signal
        
    async def produce(self, async_gen: AsyncGenerator[T, None]):
        """
        从异步生成器生产数据
        
        Args:
            async_gen: 异步生成器
        """
        if self.__is_closed:
            raise RuntimeError("流已关闭")
        self.__is_started = True
        self._stats["start_time"] = time.time()
        try:
            # 等待消费者就绪
            await self.__consumer_ready.wait()
            
            async for item in async_gen:
                # 检查控制信号
                if self.__control_signal == "stop":
                    break
                elif self.__control_signal == "paused":
                    await asyncio.sleep(0.1)
                    continue
                elif self.__control_signal == "reset":
                    raise ValueError("流被重置")
                # 设置数据
                self.__data_value = item
                self.__data_event.set()
                # 等待消费者处理
                await self.__consumer_ready.wait()
                self.__data_event.clear()
        except Exception as e:
            self.__producer_exception = e
            self._stats["errors"] += 1
            raise
        finally:
            self.__producer_done.set()
            self._stats["end_time"] = time.time()
    
    @property
    async def data(self) -> AsyncGenerator[T, None]:
        """
        消费者获取生产者生产的所有数据
        
        Yields:
            数据项
        """
        if self.__is_closed:
            raise RuntimeError("流已关闭")
        # 标记消费者就绪
        self.__consumer_ready.set()
        try:
            while True:
                # 创建两个等待任务
                data_wait_task = asyncio.create_task(self.__data_event.wait())
                done_wait_task = asyncio.create_task(self.__producer_done.wait())
                
                # 等待任意一个完成
                done, pending = await asyncio.wait(
                    [data_wait_task, done_wait_task],
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=self.streaming_task.timeout
                )
                
                # 取消未完成的任务
                for task in pending:
                    task.cancel()
                    try:
                        await task  # 确保任务真正取消
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass
                # 检查超时
                if not done:
                    raise asyncio.TimeoutError(f"流消费超时: {self.timeout}s")
                # 检查生产者是否完成
                if self.__producer_done.is_set():
                    if self.__producer_exception:
                        raise self.__producer_exception
                    break
                # 返回数据
                if self.__data_value is not None:
                    yield self.__data_value
                # 准备接收下一个数据
                self.__consumer_ready.set()
                await asyncio.sleep(0)  # 让出控制权
                
        except asyncio.CancelledError:
            # 消费者被取消
            self.send_control("stop")
            raise
        except Exception as e:
            self._consumer_exception = e
            raise
        finally:
            # 确保所有任务都被清理
            for task in [data_wait_task, done_wait_task]:
                if task and not task.done():
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass
            if self.streaming_task.auto_close:
                await self.close()
    
    def send_control(self, signal: TaskStreamingReference.StreamTaskStatus):
        """发送控制信号"""
        self.__control_signal = signal
        self.__control_event.set()
    
    async def close(self):
        """关闭流"""
        if self.__is_closed:
            return
        self.__is_closed = True
        self.send_control("stop")
        # 等待生产者完成，但不强制取消
        if self.producer_task and not self.producer_task.done():
            try:
                # 先等待一小段时间让生产者自然退出
                await asyncio.wait_for(
                    asyncio.shield(self.producer_task),
                    timeout=2.0
                )
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self.producer_task.cancel()
                try:
                    await self.producer_task
                except (asyncio.CancelledError, Exception):
                    pass
        # 清理事件
        self.__consumer_ready.set()
        self.__data_event.set()
        self.producer_task = None
        self.consumer_task = None
    
    def get_stats(self) -> TaskStreamingReference.StreamingTaskStatus:
        """获取统计信息"""
        duration = 0
        if self._stats["start_time"]:
            end = self._stats["end_time"] or time.time()
            duration = end - self._stats["start_time"]
        
        return {
            **self._stats,
            "duration": duration,
            "is_running": not self.__is_closed
        }


@dataclass
class TaskReference(Generic[T]):
    """
    任务引用
    - 表示一个已提交但尚未完成的任务
    - 提供多种方式获取结果
    """
    task_id: str
    _schedular:Any
    
    @property
    def id(self) -> str:
        """获取任务ID"""
        return self.task_id
    
    def status(self):
        """获取任务状态"""
        status = self._schedular.get_task_status(self.task_id)
        if not status:
            raise ValueError(f"任务 {self.task_id} 不存在")
        return status
    
    @property
    def is_done(self) -> bool:
        """检查任务是否完成"""
        status = self.status()
        return status["status"] != "pending"
    
    @property
    def is_success(self) -> bool:
        status = self.status()
        return status["status"] == "completed"
    
    async def wait_async(self, timeout: Optional[float] = None) -> Optional[T]:
        return await self._schedular.get_task_result_async(self.task_id, timeout=timeout)
    
    async def wait_sync(self, timeout: Optional[float] = None) -> Optional[T]:
        return await self._schedular.wait_for_task_sync(self.task_id, timeout=timeout)
    
    def result(self) -> Optional[T]:
        return asyncio.run(self.wait_sync())
    
    def then(
            self,
            success_callback: Optional[Callable[[T], Any]]=None,
            error_callback: Optional[Callable[[Exception], Any]]=None
        ) -> TaskReference[T]:
        """添加回调（当任务完成时调用）"""
        if success_callback is not None or error_callback is not None:
            async def __callback():
                try:
                    result = await self.wait_async()
                    if result is not None and success_callback is not None:
                        if iscoroutinefunction(success_callback):
                            await success_callback(result)
                        else:
                            success_callback(result)
                except Exception as e:
                    if error_callback is not None:
                        error_callback(e)
            # 在后台执行
            asyncio.create_task(__callback())
        return self
    
    def __repr__(self):
        status = self.status()["status"]
        return f"<TaskReference {self.task_id[:8]}... status={status}>"
