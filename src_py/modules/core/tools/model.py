from typing import TypedDict


class OrchestrationConfig(TypedDict):
    skill_dir: str
    max_tool_calls: int    # 最大执行次数
    exec_mode: str        # sequential / concurrent
    stop_on_fatal: bool   # 遇到 fatal 错误是否立即停止