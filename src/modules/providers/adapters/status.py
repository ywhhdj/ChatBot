"""本地模型落盘状态：是否安装、缺哪些文件、占用多大。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .registry import ProviderSpec


def _existing_names(root: Path) -> set:
    if not root.is_dir():
        return set()
    return {p.name for p in root.iterdir()}


def check_model_status(
    spec: ProviderSpec,
    *,
    expected: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """给前端用的模型状态。仅对 transport==local 的 provider 有意义。"""
    if str(spec.endpoint.get("transport") or "") != "local":
        return {"applicable": False, "installed": False}

    model_dir_raw = str(spec.endpoint.get("model_dir") or "")
    if "${" in model_dir_raw:
        return {
            "applicable": True,
            "installed": False,
            "target_dir": model_dir_raw,
            "reason": "model_dir 含未解析环境变量",
        }

    target = Path(model_dir_raw) if model_dir_raw else None
    if target is None or not target.is_dir():
        return {
            "applicable": True,
            "installed": False,
            "target_dir": model_dir_raw,
            "reason": "模型目录不存在",
        }

    download = spec.download
    expected_names = expected
    if expected_names is None:
        expected_names = list(download.get("files") or [])

    names = _existing_names(target)
    missing = [n for n in expected_names if str(n) not in names]

    total_bytes = 0
    file_count = 0
    for p in target.rglob("*"):
        if p.is_file():
            try:
                total_bytes += p.stat().st_size
                file_count += 1
            except OSError:
                continue

    return {
        "applicable": True,
        "installed": not missing and file_count > 0,
        "target_dir": model_dir_raw,
        "file_count": file_count,
        "total_mb": round(total_bytes / 1024 / 1024, 1),
        "files_present": sorted(names),
        "files_missing": missing,
    }