"""安全边界：工作区权限、服务产出目录、命令准入、敏感脱敏、轨迹保护判定。

本包不依赖具体 transport / 框架，判定逻辑均为纯函数，可独立测试。
业务模块（PPT / 技能 / shell）**只能**通过这里提供的入口访问工作区。
"""

from .workspace import (
    COMMAND_JOIN_TOKENS,
    FORBIDDEN_COMMAND_TOKENS,
    AccessVerdict,
    CommandVerdict,
    DenyReason,
    Operation,
    ScrubResult,
    Sensitivity,
    Workspace,
    WorkspaceBoundaryError,
    WorkspaceMode,
    check,
    classify_name,
    clear_workspace,
    command_verdict,
    confirm_sensitive_exposure,
    default_workspace_root,
    describe_workspace,
    ensure_workspace,
    get_workspace,
    make_output_writer,
    output_path,
    read_for_ai,
    resolve_command_path,
    resolve_in,
    scrub_text,
    select_workspace,
    service_output_dir,
)

__all__ = [
    "COMMAND_JOIN_TOKENS", "FORBIDDEN_COMMAND_TOKENS",
    "AccessVerdict", "CommandVerdict", "DenyReason", "Operation",
    "ScrubResult", "Sensitivity", "Workspace", "WorkspaceBoundaryError",
    "WorkspaceMode", "check", "classify_name", "clear_workspace",
    "command_verdict", "confirm_sensitive_exposure", "default_workspace_root",
    "describe_workspace", "ensure_workspace", "get_workspace",
    "make_output_writer", "output_path", "read_for_ai",
    "resolve_command_path", "resolve_in", "scrub_text", "select_workspace",
    "service_output_dir",
]
