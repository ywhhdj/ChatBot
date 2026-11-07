"""安全边界：工作区权限、敏感脱敏、轨迹保护判定。

本包不依赖具体 transport / 框架，判定逻辑均为纯函数，可独立测试。
"""

from .workspace import (
    AccessVerdict,
    DenyReason,
    Operation,
    ScrubResult,
    Sensitivity,
    Workspace,
    WorkspaceMode,
    check,
    classify_name,
    clear_workspace,
    confirm_sensitive_exposure,
    get_workspace,
    read_for_ai,
    scrub_text,
    select_workspace,
)

__all__ = [
    "AccessVerdict", "DenyReason", "Operation", "ScrubResult", "Sensitivity",
    "Workspace", "WorkspaceMode", "check", "classify_name", "clear_workspace",
    "confirm_sensitive_exposure", "get_workspace", "read_for_ai", "scrub_text",
    "select_workspace",
]
