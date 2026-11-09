"""端点声明模型 + handler 解析。"""
from __future__ import annotations

import importlib
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class HttpSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    method: str = "POST"
    path: str
    status_code: int = 200
    summary: str = ""
    deprecated: bool = False


class EndpointSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    op: str
    handler: str
    http: Optional[HttpSpec] = None
    tags: List[str] = Field(default_factory=list)
    desktop: bool = True
    dispatch: str = "loop"          # loop | thread | main
    timeout: float = 60.0
    enabled: bool = True
    meta: Dict[str, Any] = Field(default_factory=dict)


def resolve_handler(path: str) -> Callable:
    if ":" not in path:
        raise ValueError(f"handler 格式应为 'module.path:attr'，得到 {path}")
    mod_name, attr = path.rsplit(":", 1)
    mod = importlib.import_module(mod_name)
    fn = getattr(mod, attr, None)
    if not callable(fn):
        raise AttributeError(f"handler {path} 不可调用")
    return fn