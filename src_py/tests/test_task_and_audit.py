"""任务状态机与结构化审计回归测试 —— B1-07 / B1-08。

对应 BackendPlan B1-07（终态不被覆盖；取消/超时可解释）、
B1-08（request_id 可串联任务，日志无秘密和私人正文）、
SecurityAndAuditDesign §5（审计 schema）与 §6（request_id、日志与错误）。

只用标准库，不依赖 Rust 内核、不启动服务。

运行：

    cd src_py && python -m pytest tests/test_task_and_audit.py -v
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.core.task_state import (  # noqa: E402
    TERMINAL_STATES,
    AdvanceResult,
    StopReason,
    TaskRecord,
    TaskState,
    TransitionVerdict,
    advance,
    can_transit,
    explain,
    finish,
    is_terminal,
    normalize_state,
    state_for_reason,
    summarize,
    transition_allowed,
)
from modules.logger import audit  # noqa: E402


# ─────────────────────────────────────────────────────────────
# 状态归一化
# ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("raw,expected", [
    ("pending", TaskState.PENDING),
    ("queued", TaskState.PENDING),
    ("RUNNING", TaskState.RUNNING),
    (" Done ", TaskState.COMPLETED),
    ("cancelled", TaskState.CANCELLED),
    # 两种拼写都要认：漏掉一种就会静默走进 UNKNOWN
    ("canceled", TaskState.CANCELLED),
    ("timeout", TaskState.TIMED_OUT),
    ("timed_out", TaskState.TIMED_OUT),
])
def test_external_status_aliases(raw, expected):
    assert normalize_state(raw) == expected


def test_unknown_status_is_unknown_not_exception():
    """状态查询不该因为一个陌生字符串整体失败。"""
    assert normalize_state("something-new") == TaskState.UNKNOWN
    assert normalize_state(None) == TaskState.UNKNOWN
    assert normalize_state("") == TaskState.UNKNOWN


def test_terminal_sets():
    for st in (TaskState.COMPLETED, TaskState.FAILED,
               TaskState.CANCELLED, TaskState.TIMED_OUT):
        assert st in TERMINAL_STATES
        assert is_terminal(st)
    assert not is_terminal(TaskState.RUNNING)


# ─────────────────────────────────────────────────────────────
# 转移判定（B1-07 核心）
# ─────────────────────────────────────────────────────────────


def test_pending_to_running_allowed():
    assert can_transit(TaskState.PENDING, TaskState.RUNNING) == TransitionVerdict.ALLOWED


def test_running_to_any_terminal_allowed():
    for terminal in TERMINAL_STATES:
        assert transition_allowed(TaskState.RUNNING, terminal)


def test_terminal_is_never_overwritten():
    """核心验收：终态不被后续事件覆盖。"""
    for terminal in TERMINAL_STATES:
        for other in TaskState:
            if other == terminal:
                continue
            verdict = can_transit(terminal, other)
            assert verdict == TransitionVerdict.TERMINAL_LOCKED, (
                f"{terminal.value} -> {other.value} 必须被拒绝"
            )


def test_pending_cannot_jump_to_completed():
    """没经过 running 直接完成 = 非法。"""
    assert can_transit(TaskState.PENDING, TaskState.COMPLETED) == TransitionVerdict.INVALID


def test_same_state_is_noop_and_allowed():
    assert can_transit(TaskState.RUNNING, TaskState.RUNNING) == TransitionVerdict.NOOP
    assert transition_allowed(TaskState.RUNNING, TaskState.RUNNING)


def test_unknown_can_recover():
    """UNKNOWN 是可恢复的：外部状态一时读不出来，之后应能继续推进。
    永久卡死比短暂未知更糟。"""
    assert transition_allowed(TaskState.UNKNOWN, TaskState.RUNNING)
    assert transition_allowed(TaskState.UNKNOWN, TaskState.COMPLETED)


# ─────────────────────────────────────────────────────────────
# advance
# ─────────────────────────────────────────────────────────────


def test_advance_happy_path():
    rec = TaskRecord(task_id="t1")
    rec, res, _ = advance(rec, TaskState.RUNNING)
    assert res == AdvanceResult.OK
    assert rec.state == TaskState.RUNNING
    assert rec.revision == 1

    rec, res, _ = advance(rec, TaskState.COMPLETED, reason="completed")
    assert res == AdvanceResult.OK
    assert rec.terminal and rec.successful


def test_advance_late_event_keeps_terminal_state():
    """迟到的 chunk 不能把已完成改回 running。"""
    rec = TaskRecord(task_id="t1", state=TaskState.COMPLETED)
    new_rec, res, msg = advance(rec, TaskState.RUNNING)
    assert res == AdvanceResult.REJECTED_TERMINAL
    assert new_rec.state == TaskState.COMPLETED, "原状态必须保留"
    assert new_rec.rejected_count == 1
    assert "running" in new_rec.last_rejected


def test_advance_cancel_then_late_completion_is_rejected():
    """取消后又冒出成功结果 —— 必须拒绝。"""
    rec = TaskRecord(task_id="t1", state=TaskState.CANCELLED)
    new_rec, res, _ = advance(rec, TaskState.COMPLETED)
    assert res == AdvanceResult.REJECTED_TERMINAL
    assert new_rec.state == TaskState.CANCELLED


def test_advance_noop_does_not_bump_revision():
    rec = TaskRecord(task_id="t1", state=TaskState.RUNNING)
    new_rec, res, _ = advance(rec, TaskState.RUNNING)
    assert res == AdvanceResult.NOOP
    assert new_rec.revision == 0


def test_advance_invalid_transition():
    rec = TaskRecord(task_id="t1", state=TaskState.PENDING)
    new_rec, res, _ = advance(rec, TaskState.COMPLETED)
    assert res == AdvanceResult.REJECTED_INVALID
    assert new_rec.state == TaskState.PENDING


# ─────────────────────────────────────────────────────────────
# 结束原因（可解释性）
# ─────────────────────────────────────────────────────────────


def test_finish_maps_reason_to_state():
    rec = TaskRecord(task_id="t1", state=TaskState.RUNNING)
    rec, res, _ = finish(rec, StopReason.TIMED_OUT)
    assert rec.state == TaskState.TIMED_OUT
    assert rec.reason == "timeout"
    assert res == AdvanceResult.OK


def test_finish_reason_is_recorded_not_guessed():
    rec = TaskRecord(task_id="t1", state=TaskState.RUNNING)
    rec, _, _ = finish(rec, StopReason.CANCELLED)
    assert rec.reason == "cancelled"


@pytest.mark.parametrize("reason,expected", [
    (StopReason.COMPLETED, TaskState.COMPLETED),
    (StopReason.CANCELLED, TaskState.CANCELLED),
    (StopReason.TIMED_OUT, TaskState.TIMED_OUT),
    (StopReason.ERROR, TaskState.FAILED),
])
def test_state_for_reason(reason, expected):
    assert state_for_reason(reason) == expected


def test_retryable_reasons():
    """取消不该重试：用户主动取消后再自动跑一遍是他不想要的行为。
    超时也不该盲重试——同样输入很可能再次超时，只会放大拥塞。"""
    assert StopReason.QUEUE_FULL.retryable
    assert StopReason.ERROR.retryable
    assert not StopReason.CANCELLED.retryable
    assert not StopReason.TIMED_OUT.retryable
    assert not StopReason.COMPLETED.retryable


def test_explain_is_readable():
    rec = TaskRecord(task_id="t1", state=TaskState.TIMED_OUT, reason="timeout")
    assert "未成功" in explain(rec)
    assert "timeout" in explain(rec)

    ok = TaskRecord(task_id="t2", state=TaskState.COMPLETED)
    assert "已完成" in explain(ok)


def test_summarize_counts_states():
    records = {
        "a": TaskRecord(task_id="a", state=TaskState.COMPLETED),
        "b": TaskRecord(task_id="b", state=TaskState.FAILED),
        "c": TaskRecord(task_id="c", state=TaskState.RUNNING),
    }
    stats = summarize(records)
    assert stats["total"] == 3
    assert stats["by_state"]["completed"] == 1
    assert stats["all_terminal"] is False


# ─────────────────────────────────────────────────────────────
# 审计：脱敏（B1-08 / §6）
# ─────────────────────────────────────────────────────────────


def test_secret_keys_are_scrubbed():
    event = audit.build_event(
        audit.Action.CONFIG_CHANGE,
        metadata={"api_key": "sk-real-secret", "model": "gpt"},
    )
    assert event.metadata["api_key"] == audit.SCRUBBED
    assert "sk-real-secret" not in str(event.to_dict())
    assert event.metadata["model"] == "gpt"


@pytest.mark.parametrize("key", [
    "api_key", "API_KEY", "user_token", "password",
    "access_key", "authorization", "cookie",
])
def test_all_secret_variants_scrubbed(key):
    event = audit.build_event(audit.Action.CONFIG_CHANGE, metadata={key: "v"})
    assert event.metadata[key] == audit.SCRUBBED


def test_private_body_is_reduced_to_len_and_hash():
    """正文只留长度与 hash：够做"是不是同一条"的比对，但无法还原。"""
    event = audit.build_event(
        audit.Action.MEMORY_DELETE,
        metadata={"content": "这是一段私人对话内容"},
    )
    reduced = event.metadata["content"]
    assert isinstance(reduced, dict)
    assert reduced["len"] == len("这是一段私人对话内容")
    assert "这是一段私人对话内容" not in str(event.to_dict())


def test_newline_is_rejected_to_prevent_log_injection():
    """换行意味着可以伪造整条日志行 —— 必须拦掉。"""
    event = audit.build_event(
        audit.Action.TOOL_INVOKE,
        metadata={"note": "ok\nFAKE AUDIT LINE decision=allow"},
    )
    assert "FAKE AUDIT LINE" not in str(event.to_dict())
    assert isinstance(event.metadata["note"], dict), "含换行的值应被整体替换"


def test_long_value_is_truncated():
    event = audit.build_event(
        audit.Action.TOOL_INVOKE,
        metadata={"path": "a" * 500},
    )
    assert len(str(event.metadata["path"])) < 250


def test_metadata_key_count_limited():
    event = audit.build_event(
        audit.Action.TOOL_INVOKE,
        metadata={f"k{i}": i for i in range(100)},
    )
    assert len(event.metadata) <= audit.MAX_METADATA_KEYS + 1
    assert "_truncated_keys" in event.metadata


def test_secrets_never_in_event_fields():
    event = audit.build_event(
        audit.Action.SECRET_CHANGE,
        metadata={"secret_name": "OPENAI_KEY", "secret_value": "sk-xxx"},
    )
    payload = str(event.to_dict())
    assert "sk-xxx" not in payload
    # 只记 secret name、动作和结果，不记值（§4）
    assert event.metadata["secret_name"] == "OPENAI_KEY"


# ─────────────────────────────────────────────────────────────
# 审计：事件形状（§5）
# ─────────────────────────────────────────────────────────────


def test_event_has_required_fields():
    event = audit.build_event(
        audit.Action.MEMORY_DELETE,
        request_id="rid-1",
        session_id="s1",
        resource=audit.Resource(type=audit.ResourceType.MEMORY.value, id="42"),
    )
    payload = event.to_dict()
    for field_name in ("event_id", "ts", "request_id", "action",
                       "resource", "decision", "result", "source"):
        assert field_name in payload, f"缺字段 {field_name}"
    assert payload["schema_version"] == audit.SCHEMA_VERSION


def test_event_is_frozen():
    event = audit.build_event(audit.Action.TOOL_INVOKE)
    with pytest.raises(Exception):
        event.action = "changed"  # type: ignore[misc]


def test_parent_request_id_links_background_task():
    """后台任务保留 parent_request_id（§6），便于串联。"""
    event = audit.build_event(
        audit.Action.TASK_FINISH,
        request_id="child-1",
        parent_request_id="parent-1",
        task_id="t1",
    )
    payload = event.to_dict()
    assert payload["parent_request_id"] == "parent-1"
    assert payload["task_id"] == "t1"


def test_reason_code_is_low_cardinality():
    """reason_code 是稳定值，不含自由文本（§5）。"""
    event = audit.build_event(
        audit.Action.TOOL_DENIED,
        reason_code="exec_forbidden",
    )
    assert event.reason_code == "exec_forbidden"
    assert event.reason_code.isascii()


def test_resource_carries_id_and_count_not_body():
    res = audit.Resource(type=audit.ResourceType.MEMORY.value, id="42", count=7)
    payload = res.to_dict()
    assert payload == {"type": "memory", "id": "42", "count": 7}
    assert "content" not in payload


# ─────────────────────────────────────────────────────────────
# 审计：emit 与 sink
# ─────────────────────────────────────────────────────────────


def test_emit_goes_to_registered_sink():
    audit.reset()
    audit.clear_sinks()
    seen = []
    audit.register_sink(seen.append)
    try:
        audit.record(audit.Action.TOOL_INVOKE)
        assert len(seen) == 1
        audit.record(audit.Action.MEMORY_DELETE)
        assert len(seen) == 2
    finally:
        audit.clear_sinks()
        audit.reset()


def test_sink_failure_does_not_break_caller():
    """审计失败绝不能成为可用性风险。"""
    audit.reset()
    audit.clear_sinks()

    def _boom(_event):
        raise RuntimeError("audit store down")

    audit.register_sink(_boom)
    try:
        event = audit.record(audit.Action.TOOL_INVOKE)
        assert event is not None, "即使 sink 失败也要返回事件对象"
    finally:
        audit.clear_sinks()
        audit.reset()


def test_buffer_is_bounded():
    """审计不能无限增长（§6）。"""
    audit.reset()
    try:
        for _ in range(audit.MAX_BUFFERED + 50):
            audit.build_event(audit.Action.TOOL_INVOKE)
            audit.emit(audit.build_event(audit.Action.TOOL_INVOKE))
        stats = audit.stats()
        assert stats["buffered"] <= audit.MAX_BUFFERED
        assert stats["dropped"] > 0
    finally:
        audit.reset()


def test_recent_returns_dicts():
    audit.reset()
    try:
        audit.record(audit.Action.MEMORY_DELETE)
        rows = audit.recent(limit=5)
        assert rows and isinstance(rows[0], dict)
        assert rows[0]["action"] == "memory.delete"
    finally:
        audit.reset()


def test_action_names_are_stable_constants():
    """动作名是常量，不接受自由文本（§5）。"""
    assert audit.Action.MEMORY_DELETE == "memory.delete"
    assert audit.Action.TOOL_DENIED == "tool.denied"
    assert "." in audit.Action.SNAPSHOT_RESTORE
