"""前端 catalog：端点清单 + OpenAPI schema，前端据此生成表单。"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import Request

from ..loader import get_loader


async def api(request: Request) -> Dict[str, Any]:
    loader = get_loader()
    loader.load()
    openapi = request.app.openapi()
    paths = openapi.get("paths", {})

    items: List[Dict[str, Any]] = []
    for spec in loader.specs:
        entry: Dict[str, Any] = {
            "op": spec.op,
            "desktop": spec.desktop,
            "dispatch": spec.dispatch,
            "timeout": spec.timeout,
            "tags": spec.tags,
            "meta": spec.meta,
        }
        if spec.http is not None:
            method = spec.http.method.lower()
            path_item = paths.get(spec.http.path, {}).get(method, {})
            entry["http"] = {
                "method": spec.http.method,
                "path": spec.http.path,
                "summary": spec.http.summary,
            }
            entry["request"] = path_item.get("requestBody")
            entry["responses"] = path_item.get("responses")
        items.append(entry)

    return {
        "total": len(items),
        "groups": loader.groups,
        "endpoints": items,
    }