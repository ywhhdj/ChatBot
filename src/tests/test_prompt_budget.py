"""Prompt 纯化与 token 预算回归测试（C0-03 / B2-04）。

属于 OptimizationPlan §8 的永久回归集。只依赖标准库 + 领域模块，
不启动服务、不加载模型。

运行：

    cd src_py && python -m pytest tests/test_prompt_budget.py -v
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.core.context.budget import (  # noqa: E402
    BudgetPolicy,
    apply_budget,
    estimate_tokens,
    fit_history,
)


def seg(type_: str, priority: int, content: str) -> dict:
    return {"type": type_, "priority": priority, "content": content}


# --------------------------------------------------------------------------
# 估算口径
# --------------------------------------------------------------------------

def test_empty_text_costs_zero():
    """空段不该占预算 —— 否则每个空记忆片段都在悄悄吃掉额度。"""
    assert estimate_tokens("") == 0


def test_cjk_counts_more_than_latin():
    """中文按字计，英文约 4 字符 1 token。"""
    assert estimate_tokens("你好") >= 2
    assert estimate_tokens("hello world") < estimate_tokens("你好世界，很高兴见到你")


# --------------------------------------------------------------------------
# 预算裁剪
# --------------------------------------------------------------------------

def test_protected_segments_are_never_dropped():
    """角色身份与输出规则属于边界，再挤也不能丢（BackendDesign §10）。"""
    policy = BudgetPolicy(total_tokens=60, reserve_for_input=0)
    kept, report = apply_budget(
        [
            seg("character", 10, "你是助手。" * 50),
            seg("memory", 50, "记忆内容" * 200),
            seg("output_rules", 60, "输出要求"),
        ],
        policy,
    )
    types = [s["type"] for s in kept]
    assert "character" in types, "角色身份不可裁剪"
    assert "output_rules" in types, "输出规则不可裁剪"
    assert "memory" not in types, "记忆应被优先裁掉"


def test_report_explains_what_happened():
    """裁剪必须可解释：能回答"哪段被丢了、为什么"。"""
    kept, report = apply_budget(
        [
            seg("character", 10, "角色"),
            seg("memory", 50, "很长" * 500),
        ],
        BudgetPolicy(total_tokens=40, reserve_for_input=0),
    )
    assert not report.within_budget or report.dropped or report.truncated
    assert report.budget > 0
    assert any(s.type == "memory" for s in report.segments)


def test_within_budget_nothing_is_dropped():
    """没超预算就什么都不动 —— 裁剪不得成为默认行为。"""
    kept, report = apply_budget(
        [
            seg("character", 10, "角色"),
            seg("memory", 50, "一条记忆"),
        ],
        BudgetPolicy(total_tokens=4000, reserve_for_input=0),
    )
    assert len(kept) == 2
    assert report.dropped == []
    assert report.within_budget


def test_reserve_reduces_system_budget():
    """总额里要扣掉留给输入与生成的额度。"""
    p = BudgetPolicy(total_tokens=1000, reserve_for_input=400)
    assert p.allowed_for_system() == 600


def test_output_is_sorted_by_priority():
    """组装前必须有序，否则 prompt 段落顺序会随机漂。"""
    kept, _ = apply_budget(
        [
            seg("output_rules", 60, "c"),
            seg("character", 10, "a"),
            seg("memory", 50, "b"),
        ],
        BudgetPolicy(total_tokens=4000, reserve_for_input=0),
    )
    assert [s["priority"] for s in kept] == sorted(s["priority"] for s in kept)


def test_oversized_segment_is_truncated_not_dropped():
    """单段过大时先截断保留要点，而不是整段消失。"""
    kept, report = apply_budget(
        [
            seg("character", 10, "角色"),
            seg("memory", 50, "记忆" * 2000),
        ],
        BudgetPolicy(total_tokens=500, reserve_for_input=0),
    )
    assert any(s.type == "memory" for s in kept)
    assert report.truncated or report.used <= report.budget


# --------------------------------------------------------------------------
# 历史裁剪
# --------------------------------------------------------------------------

def test_history_keeps_recent_and_fits_budget():
    """对话历史按时序丢最旧的，但保留最近几轮（含当前轮）。"""
    history = [{"role": "user", "content": f"第{i}轮内容" * 20} for i in range(20)]
    fitted = fit_history(history, max_tokens=50, keep_last=2)

    assert len(fitted) < len(history), "应裁掉一部分"
    assert len(fitted) >= 2, "最近两轮必须保留"
    assert fitted[-1]["content"] == history[-1]["content"]


def test_history_within_budget_untouched():
    history = [{"role": "user", "content": "短消息"}]
    assert fit_history(history, max_tokens=1000) == history


def test_history_zero_budget_keeps_last():
    history = [{"role": "user", "content": f"m{i}"} for i in range(5)]
    assert len(fit_history(history, max_tokens=0, keep_last=2)) == 2
