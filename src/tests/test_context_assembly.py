"""动态上下文装配回归测试。

对应 ContextArchitecture（构建顺序与安全优先级）、§8（注入防线），
以及用户提出的"工具次数达上限要告知模型并切角色上下文"、
"PPT 等服务需切换上下文"。

只依赖标准库与 `context/assembly.py` 的纯函数，不启动服务、不调模型。

运行：

    cd src_py && python -m pytest tests/test_context_assembly.py -v
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.core.context.assembly import (  # noqa: E402
    NO_TOOLS,
    StageKind,
    ToolBudgetState,
    budget_exhausted_notice,
    next_stage,
    plan_for,
    profile_of,
    stages_for,
)
from modules.core.context.budget import BudgetPolicy  # noqa: E402
from modules.core.context.prompt import PromptBuilder  # noqa: E402
from modules.core.routes.models import RouteType  # noqa: E402


# ─────────────────────────────────────────────────────────────
# 工具额度状态
# ─────────────────────────────────────────────────────────────


def test_unlimited_budget_is_never_exhausted():
    state = ToolBudgetState(limit=-1, used=99, requested=99, skipped=0)
    assert state.unlimited
    assert not state.exhausted


def test_exhausted_requires_actually_skipped():
    """刚好用满不算打满 —— 只有真有命令被丢弃才是。"""
    full = ToolBudgetState(limit=10, used=10, requested=10, skipped=0)
    assert full.at_limit
    assert not full.exhausted, "刚好用满不需要额外告知模型"

    over = ToolBudgetState(limit=10, used=10, requested=14, skipped=4)
    assert over.exhausted


def test_exhausted_notice_states_facts_not_opinions():
    notice = budget_exhausted_notice(ToolBudgetState(limit=10, used=10, requested=14, skipped=4))
    assert "10" in notice and "4" in notice
    assert "不要再输出" in notice


# ─────────────────────────────────────────────────────────────
# 阶段推进
# ─────────────────────────────────────────────────────────────


def test_command_plan_then_normal_summary():
    nxt = next_stage(
        StageKind.COMMAND_PLAN,
        tool_state=ToolBudgetState(limit=10, used=3, requested=3, skipped=0),
        has_results=True,
    )
    assert nxt == StageKind.TOOL_SUMMARY


def test_exhausted_budget_forces_summary():
    """用户的核心诉求：额度打满 → 强制总结阶段。"""
    nxt = next_stage(
        StageKind.COMMAND_PLAN,
        tool_state=ToolBudgetState(limit=10, used=10, requested=15, skipped=5),
        has_results=True,
    )
    assert nxt == StageKind.FORCED_SUMMARY


def test_stopped_also_forces_summary():
    """超时/取消后即使额度没满，也不能让模型以为还能继续调工具。"""
    nxt = next_stage(
        StageKind.COMMAND_PLAN,
        tool_state=ToolBudgetState(limit=10, used=2, requested=2, skipped=0),
        stopped_reason="timeout",
    )
    assert nxt == StageKind.FORCED_SUMMARY


def test_no_results_falls_back_to_character_reply():
    nxt = next_stage(
        StageKind.COMMAND_PLAN,
        tool_state=NO_TOOLS,
        has_results=False,
    )
    assert nxt == StageKind.CHARACTER_REPLY


def test_summary_stages_are_terminal():
    assert next_stage(StageKind.TOOL_SUMMARY) is None
    assert next_stage(StageKind.FORCED_SUMMARY) is None
    assert next_stage(StageKind.CHARACTER_REPLY) is None


def test_stage_sequence_terminates():
    """阶段机写错会无限循环 —— 展开必须有界。"""
    seq = stages_for(
        tool_state=ToolBudgetState(limit=5, used=5, requested=9, skipped=4),
        has_results=True,
    )
    assert seq == [StageKind.COMMAND_PLAN, StageKind.FORCED_SUMMARY]
    assert len(seq) <= 8


def test_service_work_then_summary():
    assert next_stage(StageKind.SERVICE_WORK) == StageKind.TOOL_SUMMARY


# ─────────────────────────────────────────────────────────────
# 装配计划
# ─────────────────────────────────────────────────────────────


def test_command_plan_excludes_character():
    """命令阶段带人设会让模型开始寒暄而不是输出命令。"""
    plan = plan_for(StageKind.COMMAND_PLAN, route=RouteType.TOOL_CALL)
    assert plan.include_character is False
    assert plan.include_tools is True
    # 工具 schema 很长，预算必须比常规大
    assert plan.budget.total_tokens > BudgetPolicy().total_tokens


def test_forced_summary_tells_model_to_stop():
    plan = plan_for(
        StageKind.FORCED_SUMMARY,
        route=RouteType.MIXED,
        tool_state=ToolBudgetState(limit=10, used=10, requested=15, skipped=5),
    )
    assert plan.include_character, "强制总结要切回角色上下文"
    assert plan.include_task_results
    joined = " ".join(plan.directives)
    assert "额度已用尽" in joined
    assert "不要再输出任何命令" in joined
    assert "角色口吻" in joined


def test_forced_summary_without_exhaustion_uses_stopped_reason():
    plan = plan_for(
        StageKind.FORCED_SUMMARY,
        tool_state=NO_TOOLS,
        stopped_reason="timeout",
    )
    assert any("timeout" in d for d in plan.directives)


def test_tool_summary_marks_results_untrusted():
    plan = plan_for(StageKind.TOOL_SUMMARY, route=RouteType.MIXED)
    assert plan.result_trust == "untrusted_observation"
    assert any("观察数据" in d for d in plan.directives), (
        "工具结果必须标记为不可信观察，不能看起来像系统指令"
    )


def test_plan_is_frozen():
    """装配计划交出去后不该被中途改写。"""
    plan = plan_for(StageKind.TOOL_SUMMARY)
    with pytest.raises(Exception):
        plan.include_character = False  # type: ignore[misc]


# ─────────────────────────────────────────────────────────────
# 服务专属上下文（PPT）
# ─────────────────────────────────────────────────────────────


class FakePptService:
    context_profile = {
        "dedicated_stage": True,
        "system_prompt": "## PPT 服务作业约定",
        "keep_character": False,
        "keep_history": False,
        "directives": ["回复只讲产出了什么"],
        "budget": {"total_tokens": 8000, "reserve_for_input": 1024},
    }


def test_profile_read_from_mapping():
    """服务用 dict 声明，不必依赖 context 层的类型。"""
    profile = profile_of(FakePptService())
    assert profile is not None
    assert profile.active
    assert profile.keep_character is False
    assert profile.budget is not None
    assert profile.budget.total_tokens == 8000


def test_service_without_profile_is_ignored():
    class Plain:
        pass

    assert profile_of(Plain()) is None
    assert profile_of(None) is None


def test_inactive_profile_when_no_prompt():
    class Half:
        context_profile = {"dedicated_stage": True, "system_prompt": ""}

    profile = profile_of(Half())
    assert profile is not None
    assert not profile.active, "只有开关没有提示，不该切上下文"


def test_service_work_plan_uses_declared_prompt_and_budget():
    profile = profile_of(FakePptService())
    plan = plan_for(
        StageKind.SERVICE_WORK, route=RouteType.MIXED, service_profile=profile
    )
    assert "PPT" in plan.service_prompt
    assert plan.include_character is False, "PPT 作业时角色人设要让位"
    assert plan.budget.total_tokens == 8000


# ─────────────────────────────────────────────────────────────
# 指令真的进了 prompt
# ─────────────────────────────────────────────────────────────


def test_directives_enter_prompt_ahead_of_character():
    """指令必须在角色人设之前 —— 否则人设会盖过"别再输出命令"。"""
    built = PromptBuilder.build(
        character=None,
        route=RouteType.MIXED,
        user_input="帮我做个 PPT",
        task_results="已生成 deck.pptx",
        directives=["不要再输出任何命令。"],
    )
    assert "本轮执行约束" in built.system_prompt
    head = built.system_prompt.split("## 输出要求")[0]
    assert "不要再输出任何命令" in head


def test_no_directives_adds_nothing():
    built = PromptBuilder.build(character=None, route=RouteType.MIXED)
    assert "本轮执行约束" not in built.system_prompt


def test_directives_survive_budget_cutting():
    """指令属于不可裁剪段 —— 丢了就回到"继续输出命令"的错误模式。"""
    built = PromptBuilder.build(
        character=None,
        route=RouteType.MIXED,
        task_results="很长的结果" * 800,
        directives=["额度已用尽，不要再输出命令。"],
        budget_policy=BudgetPolicy(total_tokens=400, reserve_for_input=0),
    )
    assert "额度已用尽" in built.system_prompt


def test_multiple_directives_are_one_segment():
    """多条指令合并为一段：避免预算裁剪丢掉其中一条。"""
    built = PromptBuilder.build(
        character=None,
        route=RouteType.MIXED,
        directives=["第一条约束。", "第二条约束。"],
    )
    assert "第一条约束" in built.system_prompt
    assert "第二条约束" in built.system_prompt
    segments = [s for s in built.segments if s["type"] == "directive"]
    assert len(segments) == 1
