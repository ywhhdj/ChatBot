import asyncio
import logging
import os
import threading
from typing import Any, Optional
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import time

from ..runtime import StandardPaths
from ..events.data import BaseEvent
from ..events import emit,types
from ..logger import logger

os.environ["ANYIO_BACKEND"] = "custom"

class _Web:
    def __init__(
        self,
        allow_origins: Optional[list[str]] = None,
        allow_methods: Optional[list[str]] = None,
        allow_headers: Optional[list[str]] = None,
    ) -> None:
        self.app = FastAPI(title="ChatBot API")
        self.register_router()
        from ..config import get_config
        config = get_config()
        from fastapi.middleware.cors import CORSMiddleware
        #添加CORS中间件
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=allow_origins or config.web.allow_origins,
            allow_credentials=config.web.allow_credentials,
            allow_methods=allow_methods or config.web.allow_methods,
            allow_headers=allow_headers or config.web.allow_headers,
        )
    
    def get_app(self):
        return self.app
    
    #注册路由
    def register_router(self) -> None:
        from .controllers.request import req_router
        from .controllers.logger import logger_router
        from .controllers.service import service_router
        from .controllers.pipline import pipeline_router
        for router in [logger_router,service_router,pipeline_router,req_router]:
            self.app.include_router(router,prefix="/api")

    def mount_static(self, resources_path: Optional[str] = None) -> None:
        if resources_path is None:
            return
        if os.path.exists(resources_path):
            from fastapi.staticfiles import StaticFiles
            self.app.mount(
                "/",
                StaticFiles(directory=resources_path, html=True),
                name="web"
            )
            return

        @self.app.get("/")
        async def fallback():
            return HTMLResponse(
                "<h1>Static files not found. Please build the frontend.</h1>", 
                status_code=503
            )

_app:Optional[_Web]=None
_loop:Optional[asyncio.AbstractEventLoop]=None
_thread:Optional[threading.Thread]=None
_shutdown_event: Optional[asyncio.Event] = None

class UvicornLoggerHandler(logging.Handler):
    def __init__(self):
        super().__init__()
    
    def emit(self, record):
        try:
            level, msg = self.format(record)
            logger.log(level, msg)        
        except Exception:
            logger.exception(record.getMessage(), exc_info=True)
    
    def format(self, record:Any) -> tuple[int, str]:
        if hasattr(record, 'color_message'):
            record.msg = record.color_message
        if hasattr(record, 'args') and record.args:
            try:
                record.msg = record.msg % record.args
            except (TypeError, ValueError):
                pass
        return record.levelno, record.msg
        

def __app_server(host: str, port: int, debug: bool = False):
    global _app, _loop, _shutdown_event
    if _app is None:
        return
    # ★ 验证端口可用 ★
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
        sock.close()
    except OSError as e:
        logger.error(f"Port {port} is already in use. Please choose a different port.")
        return

    import uvicorn
    handler = UvicornLoggerHandler()
    handler.setFormatter(logging.Formatter('%(message)s'))
    for logger_name in ["uvicorn", "uvicorn.access", "uvicorn.error", "uvicorn.asgi"]:
        uv_logger = logging.getLogger(logger_name)
        uv_logger.handlers.clear()
        uv_logger.addHandler(handler)
        uv_logger.propagate = False
    
    config = uvicorn.Config(
        app=_app.get_app(),
        host=host,
        port=port,
        reload=True if debug else False,
        log_level="info",
        access_log=True,
        limit_max_requests=None,
        timeout_keep_alive=60,
        reload_dirs=f"{StandardPaths.get_app_root()}/api/controllers",
    )
    server = uvicorn.Server(config)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _loop = loop
    _shutdown_event = asyncio.Event()
    try:
        loop.run_until_complete(server.serve())
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        try:
            if not loop.is_closed():
                loop.run_until_complete(server.shutdown())
                loop.close()
        except Exception:
            pass
        finally:
            asyncio.set_event_loop(None)
            _loop = None
            _shutdown_event.set()
            logger.info("[Web] server stopped")

def start_web_server(
    debug: bool = False,
    host: str = "127.0.0.1",
    port: int = 8000,
    allow_origins: Optional[list[str]] = [
        "http://localhost:5173",
    ],
    allow_methods: Optional[list[str]] = ["*"],
    allow_headers: Optional[list[str]] = ["*"],
):
    global _app, _thread
    if _thread is not None and _thread.is_alive():
        return
    _app = _Web(allow_origins, allow_methods, allow_headers)
    from .controllers.websocket import websocket_connect
    from ..runtime import RuntimePath
    resources_path=RuntimePath.get_static_path()
    _app.mount_static(resources_path)
    _thread = threading.Thread(
        target=__app_server, 
        args=(host, port, debug), 
        daemon=True,
        name="WebServer"
    )
    _thread.start()
    time.sleep(0.5)

async def _shutdown():
    global _loop
    if _loop and not _loop.is_closed():
        _loop.stop()

def stop_web_server():
    global _app,_thread
    if _thread is None or not _thread.is_alive():
        return
    _app=None
    if _loop and not _loop.is_closed():
        try:
            _loop.call_soon_threadsafe(_loop.stop)
        except Exception:
            pass
    _thread.join(timeout=5)
    _app = None
    try:
        emit(BaseEvent(type=types.AppEventType.ManagerEventType.WEB_SOCKET_STOP))
    except Exception:
        pass

def get_web_app():
    if _app is None:
        raise Exception("Web app not initialized")
    return _app.get_app()

