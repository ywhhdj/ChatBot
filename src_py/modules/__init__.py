from typing import Literal
from .app import Application

__version__ = "0.1.2"

_app = None

def create_app(
    app_name: str,
    debug: bool = False,
    debug_modules: Literal["service", "pipeline", "web", "all"] = "all",
):
    global _app
    if _app is None:
        _app = Application(app_name, debug, debug_modules)
    return _app


def get_app():
    global _app
    if _app is None:
        raise Exception("App not initialized")
    return _app

__all__ = [
    "__version__"
]