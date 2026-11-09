"""服务管理器：注册、启停、配置注入、工具目录"""
from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
import threading
from functools import wraps
from typing import Any, Dict, Generic, Optional, Type, TypeVar

from ..events import types, on_event_class
from ..logger import logger
from ..manager.base import BaseManager
from ..runtime import RuntimePath
from ..utils import util
from ..utils.file import yaml
from .base import BaseService, ServiceState

T = TypeVar("T", bound=BaseService)
SERVICE_JOIN_TIMEOUT = 5.0
_LOOP_READY_TIMEOUT = 5.0
#: 异步 start_original 的最长等待。启动浏览器 / 建立首连接都在这之内完成；
#: 超时即视为启动失败并关闭本次创建的 loop，不留孤儿线程。
_START_TIMEOUT = 60.0


class _ServiceLoop:
    """单个 async 服务的持久事件循环线程。

    服务里的 Playwright / websockets / httpx 对象都绑定创建它的 loop，
    必须与 `start` 共存亡；不能用"跑完 start 就关闭"的临时 loop。
    """

    def __init__(self, name: str) -> None:
        self._ready = threading.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._closed = False
        self.thread = threading.Thread(
            target=self._run, name=f"ServiceLoop:{name}", daemon=True
        )
        self.thread.start()
        if not self._ready.wait(timeout=_LOOP_READY_TIMEOUT):
            raise RuntimeError(f"服务事件循环启动超时: {name}")

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            try:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:  # noqa: BLE001 - 停机清理不允许再抛
                pass
            finally:
                loop.close()
                asyncio.set_event_loop(None)

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            raise RuntimeError("服务事件循环已停止")
        return self._loop

    def submit(self, coro: Any):
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def close(self, timeout: float = SERVICE_JOIN_TIMEOUT) -> None:
        if self._closed:
            return
        self._closed = True
        loop = self._loop
        if loop is not None and not loop.is_closed() and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        self.thread.join(timeout)


def _coerce_config(service_id: str, raw: Any) -> Any:
    if raw is None:
        return None
    from .config import CONFIG_CLASSES, BaseServiceConfig

    if isinstance(raw, BaseServiceConfig):
        return raw
    cls = CONFIG_CLASSES.get(str(service_id))
    if cls is None:
        return raw
    if isinstance(raw, dict):
        return cls(**{k: v for k, v in raw.items() if k != "service"})
    return raw


@on_event_class([(types.AppEventType.ManagerEventType.SERVICE_STOP, "stop")])
class ServiceManager(Generic[T], BaseManager):
    def __init__(self) -> None:
        if self._initialized:
            return
        self.services: Dict[str, T] = {}
        self.service_threads: Dict[str, Dict[str, Any]] = {}
        self.services_config: Dict[str, Any] = {}
        self._state_lock = threading.RLock()
        self._stopping: set = set()
        self._tools_cache: Optional[list] = None
        self._initialized = True

    # ---------- 注册 ----------

    def register_service(self, service_id: str, service: T) -> str:
        with self._state_lock:
            existing = self.services.get(service_id)
            if existing is not None and existing is not service:
                logger.warning(f"[Service] {service_id} 被重新注册，覆盖旧实例")
            self.services[service_id] = service
            stored = self.services_config.get(service_id)
            self._tools_cache = None
        if stored is not None:
            service.config = _coerce_config(service_id, stored)
        return service_id

    def unregister(self, service_id: str) -> str:
        with self._state_lock:
            self.services.pop(service_id, None)
            self.service_threads.pop(service_id, None)
            self._tools_cache = None
        return service_id

    def is_registered(self, service_id: str) -> bool:
        return str(service_id) in self.services

    # ---------- 配置 ----------

    def set_service_config(self, service_id: str, config: Dict[str, Any]) -> Any:
        """预存配置；若服务已注册则立即注入。返回配置对象。"""
        obj = _coerce_config(service_id, config)
        with self._state_lock:
            self.services_config[service_id] = obj
            service = self.services.get(service_id)
        if service is not None and obj is not None:
            self._apply_config(service, obj)
        return obj

    @staticmethod
    def _apply_config(service: T, config: Any) -> None:
        old = service.config
        service.config = config
        hook = getattr(service, "on_config_change", None)
        if callable(hook):
            try:
                before = old.to_dict() if hasattr(old, "to_dict") else dict(old or {})
                after = config.to_dict() if hasattr(config, "to_dict") else dict(config or {})
                hook(before, after)
            except Exception as exc:  # noqa: BLE001 - 钩子失败不影响配置生效
                logger.debug(f"[Service] on_config_change 失败: {exc}")

    def update_service_config(self, service_id: str, new_config: Optional[Any] = None) -> bool:
        if new_config is None:
            return False
        self.set_service_config(service_id, new_config)
        return True

    def get_service_config(self, service_id: str) -> Any:
        with self._state_lock:
            service = self.services.get(service_id)
            stored = self.services_config.get(service_id)
        if service is None:
            raise ValueError(f"Service {service_id} not found")
        config = service.config
        if config is None:
            config = stored
        if config is None:
            config = _coerce_config(service_id, {})
        if config is not None and service.config is None:
            service.config = config
        if config is None:
            raise ValueError(f"Service {service_id} 没有可用配置")
        return config

    def get_config(self, service_id: str) -> Any:
        return self.get_service_config(service_id)

    # ---------- 主线程服务 ----------

    @staticmethod
    def _is_main_thread_service(service: T) -> bool:
        return bool(getattr(service, "main_thread", False))

    def _run_on_main_thread(self, service: T, method_name: str, args, kwargs) -> bool:
        fn = getattr(service, method_name, None)
        if fn is None:
            return False
        if inspect.iscoroutinefunction(fn):
            # 同步派发器无法 await 协程；静默丢弃比抛异常更糟，直接记错误。
            logger.error(f"[Service] 主线程服务不支持异步 {method_name}")
            return False
        if threading.current_thread() is threading.main_thread():
            fn(*args, **kwargs)
            return True
        try:
            from ..ui.dispatcher import get_main_thread_dispatcher

            get_main_thread_dispatcher().run_on_main_thread(fn, *args, **kwargs)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[Service] dispatch {method_name} to main thread failed: {exc}")
            return False

    # ---------- 启停 ----------

    def start_service(self, service_id: str = "", *args, **kwargs) -> bool:
        with self._state_lock:
            service = self.services.get(service_id)
        if service is None:
            return False
        if service.state == ServiceState.RUNNING:
            logger.warning(f"[Service] {service_id} 已在运行")
            return False

        start_fn = getattr(service, "start_original", None)
        if start_fn is None:
            service.state = ServiceState.ERROR
            return False

        try:
            if self._is_main_thread_service(service):
                if inspect.iscoroutinefunction(start_fn):
                    raise RuntimeError("主线程服务不支持异步 start")
                ok = self._run_on_main_thread(service, "start_original", args, kwargs)
                service.state = ServiceState.RUNNING if ok else ServiceState.ERROR
                return ok

            if inspect.iscoroutinefunction(start_fn):
                holder = _ServiceLoop(str(getattr(service, "name", service_id) or service_id))
                fut = holder.submit(start_fn(*args, **kwargs))
                # 启动必须"等到真的起来"再回成功：否则 controller 返回
                # "已启动"时 Playwright / websockets 可能还没建好，稍后失败
                # 只能靠回调偷偷把状态改成 ERROR。
                try:
                    fut.result(timeout=_START_TIMEOUT)
                except concurrent.futures.TimeoutError:
                    holder.close()
                    raise RuntimeError(f"异步启动超过 {_START_TIMEOUT:.0f}s") from None
                except Exception:
                    holder.close()
                    raise
                with self._state_lock:
                    self.service_threads[service_id] = {
                        "loop": holder,
                        "thread": holder.thread,
                    }
                service.state = ServiceState.RUNNING
                return True

            thread = util.create_daemon_thread(
                start_fn,
                name=str(getattr(service, "name", service_id) or service_id),
                args=args,
                kwargs=kwargs,
            )
            with self._state_lock:
                self.service_threads[service_id] = {"loop": None, "thread": thread}
            thread.start()
            service.state = ServiceState.RUNNING
            return True
        except Exception as exc:  # noqa: BLE001
            service.state = ServiceState.ERROR
            logger.error(f"[Service] 启动 {service_id} 失败: {exc}")
            return False

    def get_service_loop(self, service_id: str) -> Optional[asyncio.AbstractEventLoop]:
        """供命令执行器把 async 服务方法投递回服务自己的 loop。"""
        with self._state_lock:
            holder = (self.service_threads.get(service_id) or {}).get("loop")
        if holder is None:
            return None
        try:
            return holder.loop
        except RuntimeError:
            return None

    def stop_service(self, service_id: str, *args, **kwargs) -> bool:
        with self._state_lock:
            service = self.services.get(service_id)
            entry = dict(self.service_threads.get(service_id) or {})
            if service_id in self._stopping:
                return False  # connect() 的 finally 可能回调 stop，禁止递归
            self._stopping.add(service_id)
        if service is None:
            with self._state_lock:
                self._stopping.discard(service_id)
            return False

        error: Optional[BaseException] = None
        holder = entry.get("loop")
        try:
            stop_fn = getattr(service, "stop_original", None)
            if stop_fn is not None:
                if inspect.iscoroutinefunction(stop_fn):
                    if holder is not None:
                        holder.submit(stop_fn(*args, **kwargs)).result(
                            timeout=SERVICE_JOIN_TIMEOUT
                        )
                    else:
                        # 未通过管理器启动的 async 服务：在调用线程（线程池，
                        # 无运行中 loop）用临时 loop 跑完 stop。
                        asyncio.run(stop_fn(*args, **kwargs))
                elif self._is_main_thread_service(service):
                    self._run_on_main_thread(service, "stop_original", args, kwargs)
                else:
                    stop_fn(*args, **kwargs)

            thread = entry.get("thread")
            if (
                thread is not None
                and thread is not threading.current_thread()
                and thread.is_alive()
            ):
                try:
                    from ..ui.dispatcher import join_with_pump

                    joined = join_with_pump(thread, SERVICE_JOIN_TIMEOUT)
                except Exception:  # noqa: BLE001
                    thread.join(SERVICE_JOIN_TIMEOUT)
                    joined = not thread.is_alive()
                if not joined:
                    logger.warning(
                        f"[Service] {service_id} 线程未在 {SERVICE_JOIN_TIMEOUT}s 内退出"
                    )
        except Exception as exc:  # noqa: BLE001
            error = exc
            logger.error(f"[Service] 停止 {service_id} 失败: {exc}")
        finally:
            if holder is not None:
                try:
                    holder.close(SERVICE_JOIN_TIMEOUT)
                except Exception as exc:  # noqa: BLE001
                    logger.debug(f"[Service] 关闭 {service_id} loop 失败: {exc}")
            with self._state_lock:
                self.service_threads.pop(service_id, None)
                self._stopping.discard(service_id)
            service.state = ServiceState.ERROR if error else ServiceState.STOPPED
        return error is None

    def close_service(self, service_id: str, *args, **kwargs) -> None:
        self.stop_service(service_id, *args, **kwargs)
        self.unregister(service_id)

    # ---------- 查询 ----------

    def get_service_names(self) -> list:
        return [service.name for service in self.services.values()]

    def get_service_info(self, service_id: str) -> Optional[Dict[str, Any]]:
        service = self.services.get(service_id)
        if service is None:
            return None
        return {
            "name": service.name,
            "description": service.description,
            "state": service.state,
            "config": self.get_service_config(service_id),
            "main_thread": self._is_main_thread_service(service),
        }

    def get_all_service_infos(self) -> list:
        infos = []
        for service_id in list(self.services):
            info = self.get_service_info(service_id)
            if info is not None:
                infos.append(info)
        return infos

    def get_service(self, service_id: str) -> T:
        service = self.services.get(service_id)
        if service is None:
            raise ValueError(f"Service {service_id} not registered")
        return service

    def get_service_state(self, service_id: str) -> str:
        return self.get_service(service_id).state

    # ---------- 工具目录 ----------

    def get_service_tool(self, service_id: str):
        return self.get_service(service_id).get_tools()

    def get_tools(self) -> list:
        with self._state_lock:
            if self._tools_cache is not None:
                return list(self._tools_cache)
            services = list(self.services.values())
        tools = []
        for service in services:
            try:
                declared = service.get_tools()
            except Exception as exc:  # noqa: BLE001 - 单个服务不影响整份目录
                logger.warning(f"[Service] 读取 {service.name} 工具声明失败: {exc}")
                continue
            if declared is None:
                continue
            tools.append({"service": service.name, "tools": declared})
        with self._state_lock:
            if self._tools_cache is None:
                self._tools_cache = tools
        return list(self._tools_cache)

    def get_ui_service_description(self, service_id: str) -> Dict[str, Any]:
        from .config import CONFIG_CLASSES

        cls = CONFIG_CLASSES.get(str(service_id))
        if cls is None:
            raise ValueError(f"未知服务配置类型: {service_id}")
        return cls().get_ui_config_items()

    # ---------- 停机 ----------

    def stop(self) -> None:
        service_ids = list(self.services)
        configs: Dict[str, Any] = {}
        for sid in service_ids:
            try:
                cfg = self.get_service_config(sid)
                configs[sid] = cfg.to_dict() if hasattr(cfg, "to_dict") else cfg
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"[Service] 读取 {sid} 配置失败: {exc}")
        try:
            if configs:
                yaml.write_yaml(RuntimePath.get_service_config_file_path(), configs)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[Service] 服务配置落盘失败: {exc}")

        for sid in service_ids:
            try:
                self.close_service(sid)
            except Exception as exc:  # noqa: BLE001
                logger.error(f"[Service] close {sid} failed: {exc}")

        # 同步服务（PPT 大纲）使用的共享持久 loop 也要在停机时释放，
        # 否则 daemon 线程与绑定其上的 httpx 连接会一直挂到进程退出。
        try:
            from ._async import shutdown_service_loop

            shutdown_service_loop()
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[Service] 共享 loop 关闭失败: {exc}")


service_manager = ServiceManager()


class ServiceDecorator(Generic[T]):
    """把生命周期方法交给 ServiceManager，并保留原始实现为 *_original。"""

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


def Service(id: Optional[str] = None) -> ServiceDecorator:
    """服务注册装饰器。唯一正式入口，不再提供 `services.service.decorator`。"""
    return ServiceDecorator(id)
