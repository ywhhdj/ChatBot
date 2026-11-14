import asyncio
import logging
import os
from pathlib import Path
import threading
from typing import Any, Optional

from ..runtime import RuntimePath
from ..logger import logger
from ..ui.dispatcher import join_with_pump

LOCAL_ORIGIN_RE = r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$"

def port_available(host: str, port: int) -> bool:
    """探测端口。必须带 SO_REUSEADDR，否则探测用的 socket 进入 TIME_WAIT 后，
    紧跟其后的 uvicorn bind 反而会失败——探测本身制造了问题。"""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
        return True
    except OSError as e:
        logger.error(f"[Web] port {port} bind failed: {e}")
        return False
    finally:
        sock.close()

class UvicornLoggerHandler(logging.Handler):
    """把 uvicorn 日志接进应用日志链路"""

    def __init__(self):
        super().__init__()

    def emit(self, record):
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001 - args 格式化失败时退回原始 msg
            msg = str(getattr(record, "msg", "") or "")
        try:
            logger.log(record.levelno, msg)
        except Exception:
            try:
                logger.error(f"[Web] uvicorn log bridge failed: {msg}")
            except Exception:  # noqa: BLE001
                pass

    def format(self, record: Any) -> tuple[int, str]:
        """保留给外部调用；不再修改 record.msg。"""
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001
            msg = str(getattr(record, "msg", "") or "")
        return record.levelno, msg

class Web:
    def __init__(self,app_name: str) -> None:
        from fastapi import FastAPI
        self.app = FastAPI(title=app_name + " API")
        self.loop=None
        self.server = None
        self.thread:Optional[threading.Thread] = None
        self.event:Optional[threading.Event] = None
        # 路由 / 中间件 / 静态挂载只能装一次；重复 start 会挂出重复路由。
        self._initialized = False
    
    def get_app(self):
        return self.app

    def __register_router(self) -> None:
        from .controllers import register_all_routers
        from .response import (
            install_exception_handlers,
            install_request_id_middleware,
        )
        install_request_id_middleware(self.app)
        register_all_routers(self.app)
        install_exception_handlers(self.app)

    def __mount_static(self, resources_path: Optional[str|Path] = None) -> None:
        # 必须是「目录」：原来传的是 <static>/index.html 这个**文件**，
        # os.path.exists 为真，StaticFiles(directory=<file>) 会直接抛
        # RuntimeError，Web 服务一启动就挂。
        if resources_path is None or not os.path.isdir(resources_path):
            self.__mount_fallback()
            return
        from fastapi.staticfiles import StaticFiles
        self.app.mount(
            "/",
            StaticFiles(directory=str(resources_path), html=True),
            name="web"
        )

    def __mount_fallback(self) -> None:
        @self.app.get("/")
        async def fallback():
            from fastapi.responses import HTMLResponse
            return HTMLResponse(
                "<h1>Static files not found. Please build the frontend.</h1>",
                status_code=503
            )


    def __web_thread_main(self,host: str, port: int) -> None:
        handler = UvicornLoggerHandler()
        for logger_name in ["uvicorn", "uvicorn.access", "uvicorn.error", "uvicorn.asgi"]:
            uv_logger = logging.getLogger(logger_name)
            uv_logger.handlers.clear()
            uv_logger.addHandler(handler)
            uv_logger.propagate = False

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.loop = loop
        self.__bind_websocket_manager(loop)

        import uvicorn
        config = uvicorn.Config(
            app=self.get_app(),
            host=host,
            port=port,
            reload=False,
            log_level="info",
            access_log=True,
            limit_max_requests=None,
            timeout_keep_alive=60
        )

        self.server = uvicorn.Server(config)

        async def _serve():
            if self.server is None:
                raise Exception("Server not initialized")
            task = asyncio.create_task(self.server.serve())
            # 等 server 真正 listen 之后再放就绪信号，
            # 否则调用方一就绪就发请求会直接 ConnectionRefused
            for _ in range(500):
                if self.server.started:
                    break
                await asyncio.sleep(0.02)
            self.event.set()  # type: ignore[union-attr]
            await task

        try:
            loop.run_until_complete(_serve())
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            asyncio.set_event_loop(None)
            loop.close()
            self.loop = None
            self.server = None
            try:
                from .controllers.websocket.manager import get_websocket_manager
                manager = get_websocket_manager()
                manager.stop()
                manager.bind_loop(None)
            except Exception as e:
                logger.debug(f"[Web] unbind websocket manager failed: {e}")
            if self.event is not None:
                self.event.set()  # 防止调用方永久阻塞在 wait_ready
            logger.info("[Web] web thread exited")
    
    @staticmethod
    def __bind_websocket_manager(loop: asyncio.AbstractEventLoop) -> None:
        """绑定 Web loop 并启动 WebSocket 管理器。

        cleanup 任务必须建在这个长期存活的 loop 上。
        若在未绑定时创建，会被挂到临时 loop，随 loop 销毁而永不执行。
        """
        try:
            from .controllers.websocket.manager import get_websocket_manager
            manager = get_websocket_manager()
            manager.bind_loop(loop)
            manager.start()
        except Exception as e:
            logger.error(f"[Web] bind websocket manager failed: {e}")

    def init(
        self,
        allow_origins: Optional[list[str]] = None,
        allow_methods: Optional[list[str]] = ["*"],
        allow_headers: Optional[list[str]] = ["*"]
    ):
        if self._initialized:
            return
        self.__register_router()
        from ..config import get_config
        config = get_config().web
        from fastapi.middleware.cors import CORSMiddleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=allow_origins or config.allow_origins,
            allow_origin_regex=LOCAL_ORIGIN_RE,
            allow_credentials=config.allow_credentials,
            allow_methods=allow_methods or config.allow_methods,
            allow_headers=allow_headers or config.allow_headers,
        )
        from .controllers.websocket import register_websocket_routes  # noqa: F401
        register_websocket_routes(self.get_app())
        self.__mount_static(RuntimePath.get_web_resources_dir())
        self._initialized = True
    
    @property
    def is_ready(self) -> bool:
        server = self.server
        return bool(
            self.event is not None
            and self.event.is_set()
            and server is not None
            and getattr(server, "started", False)
        )

    def start_web_in_thread(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        allow_origins: Optional[list[str]] = None,
        allow_methods: Optional[list[str]] = ["*"],
        allow_headers: Optional[list[str]] = ["*"],
        wait_ready: bool = True,
        timeout: float = 10.0
    ) -> bool:
        if self.thread is not None and self.thread.is_alive():
            logger.warning("[Web] server thread already running")
            return True
        if allow_origins is None:
            allow_origins = ["http://localhost:5173"]
        if not port_available(host, port):
            logger.error(f"[Web] port {port} is already in use, web server not started")
            return False
        self.init(allow_origins, allow_methods, allow_headers)
        self.event = threading.Event()
        self.thread = threading.Thread(
            target=self.__web_thread_main,
            args=(host, port),
            name="WebServerLoop",
            daemon=True,
        )
        self.thread.start()
        if wait_ready and not self.event.wait(timeout):
            logger.error("[Web] server failed to become ready in time")
            return False
        if wait_ready and not self.is_ready:
            # event 被 finally 兜底 set() 了，但 uvicorn 其实没 listen 成功
            logger.error("[Web] server did not start listening, web disabled")
            return False
        logger.info(f"[Web] serving on http://{host}:{port} (thread={self.thread.name})")
        return True
    
    def stop(self) -> None:
        if self.server is not None:
            self.server.should_exit = True
        if self.loop is not None:
            try:
                self.loop.call_soon_threadsafe(lambda: None)
            except RuntimeError:
                pass
    
    def join(self, timeout: float = 10.0) -> bool:
        """同步等待 Web 线程结束。

        调用方是主线程时用 join_with_pump，保证等待期间 Qt 事件仍在派发，
        避免「主线程等 web、web 请求等主线程」的死锁。
        """
        self.stop()
        if self.thread is None:
            return True
        if not self.thread.is_alive():
            self.thread = None
            return True
        if threading.current_thread() is self.thread:
            logger.warning("[Web] refuse to join web thread from itself")
            return False

        try:
            ok = join_with_pump(self.thread, timeout)
        except Exception:
            self.thread.join(timeout)
            ok = not self.thread.is_alive()
        if not ok:
            logger.warning(f"[Web] web thread did not stop within {timeout}s")
        self.thread = None
        return ok

    async def shutdown(self,timeout: float = 10.0) -> None:
        """优雅停机：先让 uvicorn 自己跑完 shutdown（释放端口与连接），
        超时或当前正被取消时才动用 cancel()。"""
        self.stop()
        if self.thread is None or not self.thread.is_alive():
            self.thread = None
            return
        if threading.current_thread() is self.thread:
            return
        # 用 to_thread 避免阻塞调用方的事件循环
        await asyncio.to_thread(join_with_pump, self.thread, timeout)
        if self.thread is not None and self.thread.is_alive():
            logger.warning(f"[Web] web thread did not stop within {timeout}s")
        self.thread = None

_app: Optional[Web] = None

def get_web(app_name: str="ChatBot"):
    global _app
    if _app is None:
        _app = Web(app_name)
    return _app

def get_web_app():
    if _app is None:
        raise Exception("Web app not initialized")
    return _app.get_app()

def run_web(
    app_name: str,
    host: Optional[str] = None,
    port: Optional[int] = None,
    allow_origins: Optional[list[str]] = None,
    allow_methods: Optional[list[str]] = None,
    allow_headers: Optional[list[str]] = None,
    wait_ready: bool = True,
    timeout: float = 10.0
) -> bool:
    """按 app.conf 的 [Web] 段启动 HTTP 服务"""
    try:
        from ..config import get_config

        cfg = get_config().web
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[Web] 读取 Web 配置失败，使用默认值: {exc}")
        cfg = None

    def _pick(explicit, attr, default):
        if explicit is not None:
            return explicit
        value = getattr(cfg, attr, None) if cfg is not None else None
        return value if value not in (None, "") else default

    host = str(_pick(host, "host", "127.0.0.1"))
    port = int(_pick(port, "port", 8000))
    allow_origins = _pick(allow_origins, "allow_origins", ["*"])
    allow_methods = _pick(allow_methods, "allow_methods", ["*"])
    allow_headers = _pick(allow_headers, "allow_headers", ["*"])
    if isinstance(allow_origins, str):
        allow_origins = [allow_origins]
    if isinstance(allow_methods, str):
        allow_methods = [allow_methods]
    if isinstance(allow_headers, str):
        allow_headers = [allow_headers]

    web = get_web(app_name)
    ok = web.start_web_in_thread(
        host, port, allow_origins, allow_methods, allow_headers, wait_ready, timeout
    )
    if not ok:
        logger.warning("[Web] web server not started")
    return ok


def get_web_loop():
    if _app is None:
        raise Exception("Web app not initialized")
    return _app.loop

def stop_web_server() -> None:
    global _app
    if _app is not None:
        _app.stop()

def join_web_thread(timeout: float = 10.0) -> bool:
    if _app is None:
        return True
    return _app.join(timeout)


async def shutdown_web_server(timeout: float = 10.0) -> None:
    if _app is not None:
        await _app.shutdown(timeout)
