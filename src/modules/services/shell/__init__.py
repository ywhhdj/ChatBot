"""受控 shell 命令服务。

- `commands.py`：平台命令映射、白名单、命令计划（纯判定，无框架依赖）
- `service.py`：`ShellService`，注册为服务 id `shell`，负责工作区边界与进程执行

`commands.py` 会被策略层与解析层间接依赖，因此这里**不**在包初始化时
"""

from .commands import CommandPlan, ShellPlatform, plan_command, shell_spec

__all__ = [
    "CommandPlan", "ShellPlatform", "plan_command", "shell_spec", "ShellService",
]


def __getattr__(name: str):
    if name == "ShellService":
        from .service import ShellService

        return ShellService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
