"""上下文隔离回归测试（C0-02 / C0-04 / C0-05）。

这是 OptimizationPlan §8 列出的**永久回归集**之一：
"交错并发的两个 session，prompt、记忆、工具结果零串线"。

只依赖标准库 + pydantic，不启动服务、不加载模型。
运行：

    cd src_py && python -m pytest tests/test_context_isolation.py -v
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src_py.modules.core.context.request import RequestContext, set_current, reset_current  # noqa: E402
from src_py.modules.core.context.store import ContextStore  # noqa: E402
from src_py.modules.core.context.user import UserContext  # noqa: E402
from modules.models import MessageContext, Role  # noqa: E402


def msg(session_id: str, role: str, content: str) -> MessageContext:
    return MessageContext(
        id=f"{session_id}-{content}",
        timestamp=datetime.now().timestamp(),
        role=role,
        content=content,
        session_id=session_id,
        tokens=1,
    )


# --------------------------------------------------------------------------
# session 分桶
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_interleaved_sessions_never_mix():
    """两个会话交错写入，各自读取零串线。"""
    store = ContextStore(max_messages=10)

    async def talk(sid: str, n: int) -> None:
        for i in range(n):
            await store.add(msg(sid, Role.USER, f"{sid}-u{i}"))
            await store.add(msg(sid, Role.ASSISTANT, f"{sid}-a{i}"))
            await asyncio.sleep(0)  # 强制让出，制造交错

    await asyncio.gather(talk("A", 15), talk("B", 15), talk("C", 15))

    for sid in ("A", "B", "C"):
        got = store.get_dialogue(sid)
        assert got, f"{sid} 应有消息"
        assert all(x["content"].startswith(f"{sid}-") for x in got), (
            f"{sid} 的上下文混入了其他会话: {got}"
        )


@pytest.mark.asyncio
async def test_read_requires_session_scope():
    """没有 session 作用域就没有结果——不存在"返回全部"的入口。"""
    store = ContextStore()
    await store.add(msg("A", Role.USER, "a1"))
    await store.add(msg("B", Role.USER, "b1"))

    assert len(store.get_dialogue("A")) == 1
    assert len(store.get_dialogue("B")) == 1
    # 未写入过的会话返回空，而不是回退到全量
    assert store.get_dialogue("nobody") == []


@pytest.mark.asyncio
async def test_clear_only_target_session():
    """C0-05：切会话/清上下文只影响指定的那个。"""
    store = ContextStore()
    await store.add(msg("A", Role.USER, "a1"))
    await store.add(msg("B", Role.USER, "b1"))

    removed = await store.clear("A")
    assert removed == 1
    assert store.get_dialogue("A") == []
    assert len(store.get_dialogue("B")) == 1, "清 A 不应动到 B"


@pytest.mark.asyncio
async def test_per_session_locks_do_not_serialize():
    """不同 session 用不同的锁：A 持锁不应阻塞 B 写入。"""
    store = ContextStore()
    released = asyncio.Event()

    async def hold_a():
        async with store._locks.for_session("A"):  # noqa: SLF001
            await asyncio.sleep(0.3)
            released.set()

    task = asyncio.create_task(hold_a())
    await asyncio.sleep(0.05)

    started = time.monotonic()
    # B 若与 A 共用一把锁，这里会等到 0.3s 之后
    await asyncio.wait_for(store.add(msg("B", Role.USER, "b")), timeout=0.2)
    assert not released.is_set(), "B 的写入不应等 A 释放锁"
    assert time.monotonic() - started < 0.2

    await task


# --------------------------------------------------------------------------
# 记忆片段：瞬态、每轮覆盖、不进对话窗口
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_memory_snippets_are_transient():
    """C0-04：记忆每轮整体覆盖，不会随轮次无限堆积。"""
    store = ContextStore()
    for turn in range(5):
        store.set_memory_snippets("A", [{"title": f"轮{turn}", "content": "x"}])

    snippets = store.get_memory_snippets("A")
    assert len(snippets) == 1, f"应只剩本轮片段，实际 {len(snippets)} 条"
    assert snippets[0]["title"] == "轮4"

    # 片段不算对话
    assert store.get_dialogue("A") == []


@pytest.mark.asyncio
async def test_memory_snippets_scoped_by_session():
    store = ContextStore()
    store.set_memory_snippets("A", [{"title": "A 的记忆"}])
    store.set_memory_snippets("B", [{"title": "B 的记忆"}])

    assert store.get_memory_snippets("A")[0]["title"] == "A 的记忆"
    assert store.get_memory_snippets("B")[0]["title"] == "B 的记忆"


# --------------------------------------------------------------------------
# UserContext 门面
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_user_context_filters_by_session():
    """旧实现的致命点：get_current_messages() 返回所有会话的消息。"""
    ctx = UserContext()
    await ctx.clear_session("s1")
    await ctx.clear_session("s2")

    await ctx.add_user_message("会话1的话", session_id="s1")
    await ctx.add_user_message("会话2的话", session_id="s2")

    s1 = ctx.get_current_messages(session_id="s1")
    s2 = ctx.get_current_messages(session_id="s2")

    assert [m["content"] for m in s1] == ["会话1的话"]
    assert [m["content"] for m in s2] == ["会话2的话"]


@pytest.mark.asyncio
async def test_user_context_falls_back_to_request_context():
    """不传 session_id 时取当前 RequestContext，而不是"全部会话"。"""
    ctx = UserContext()
    await ctx.clear_session("from-req")

    request = RequestContext.create(session_id="from-req")
    token = set_current(request)
    try:
        await ctx.add_user_message("自动归属", session_id="from-req")
        got = ctx.get_current_messages()  # 不传参
        assert [m["content"] for m in got] == ["自动归属"]
    finally:
        reset_current(token)


# --------------------------------------------------------------------------
# RequestContext
# --------------------------------------------------------------------------

def test_request_context_timeout_and_cancel():
    r = RequestContext.create(session_id="s", timeout=1.0)
    assert r.remaining() is not None and 0 < r.remaining() <= 1.0
    assert not r.expired()

    r2 = RequestContext.create(session_id="s", timeout=-1)  # 已过期
    assert r2.expired()
    assert r2.remaining() == 0.0, "超时后剩余量应为 0，不返回负数"

    r3 = RequestContext.create(session_id="s")
    assert r3.remaining() is None, "不限时返回 None"
    r3.cancel()
    assert r3.cancelled()


def test_request_context_is_immutable_and_bindable():
    r = RequestContext.create(session_id="a", character_id="c1")
    sub = r.bind(session_id="b")
    assert r.session_id == "a", "bind 不得改动原上下文"
    assert sub.session_id == "b"
    assert sub.request_id == r.request_id, "子上下文应沿用同一个 request_id"
    assert sub.character_id == "c1"
