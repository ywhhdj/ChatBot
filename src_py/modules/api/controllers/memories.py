"""记忆接口：三层记忆、摘要、语义检索、压缩记忆、衰减、统计。

所有端点返回 `ApiResponse[T]`，`T` 为 `api/dto.py` 中已声明的记忆 DTO；
不再返回裸 `Dict`，便于前端/桌面 bridge 共用类型。

**关键：记忆系统必须在同一个事件循环里调用。**

`storage` 内部持有 `asyncio.Lock`（MarkdownStorage 惰性创建）与
`asyncio.Queue`（SQLiteFAISSStorage 的 worker 队列），它们会绑定首次
使用的 loop。初始化发生在调度器 loop（`chat.ensure_initialized` 走
`async_task_scheduler`），因此这里的所有调用也统一提交到调度器 loop ——
既避免 `attached to a different loop`，也不会占住 Web loop。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query

from ..dto import (
    CompressedItem,
    DetailedMemoryItem,
    MemoryCompressedListData,
    MemoryDecayData,
    MemoryDeleteData,
    MemoryFlushData,
    MemoryLayersData,
    MemoryLongTermData,
    MemorySearchData,
    MemoryShortTermData,
    MemoryStatsData,
)
from ..requests import MemorySearchRequest
from ..response import ApiError, ApiResponse, success
from .._common import run_in_scheduler

DEFAULT_TIMEOUT = 60.0


def _memory():
    from ...memory.main import HybridMemorySystem

    sysm = HybridMemorySystem.instance()
    if not sysm or not getattr(sysm, "_initialized", False):
        raise ApiError.not_initialized(
            "记忆系统", "尚未初始化，请等待应用启动完成或先发起一次对话"
        )
    return sysm


def _detailed(rows: Optional[List[Dict[str, Any]]]) -> List[DetailedMemoryItem]:
    items: List[DetailedMemoryItem] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        items.append(
            DetailedMemoryItem(
                id=str(row.get("id", "") or ""),
                content=str(row.get("content", "") or ""),
                score=float(row.get("score", 0.0) or 0.0),
                role=str(row.get("role", "") or ""),
                created_at=float(row.get("created_at", 0.0) or 0.0),
            )
        )
    return items


def _compressed(rows: Optional[List[Any]]) -> List[CompressedItem]:
    items: List[CompressedItem] = []
    for row in rows or []:
        data = row.to_dict() if hasattr(row, "to_dict") else dict(row)
        meta = data.get("metadata") or {}
        items.append(
            CompressedItem(
                id=str(data.get("id", "") or ""),
                summary=str(data.get("summary", "") or ""),
                created_at=float(data.get("created_at", 0.0) or 0.0),
                original_count=int(meta.get("original_count", 0) or 0)
                if isinstance(meta, dict)
                else 0,
            )
        )
    return items


# --------------------------------------------------------------------------
# 三层记忆
# --------------------------------------------------------------------------
async def layers(
    session_id: str = Query("default"),
    query: str = Query("", description="留空则不检索详细层，延迟更低"),
    detail_top_k: int = Query(8, ge=0, le=50),
    summary_limit: int = Query(8, ge=1, le=50),
) -> ApiResponse[MemoryLayersData]:
    """三层记忆（短期 / 长期 / 详细），供 prompt 注入。"""
    sysm = _memory()

    async def _call():
        return await sysm.get_memory_layers(
            query=query,
            session_id=session_id,
            detail_top_k=detail_top_k,
            summary_limit=summary_limit,
            is_query_detailed_items=bool(query),
        )

    try:
        data = await run_in_scheduler(_call, timeout=DEFAULT_TIMEOUT)
    except Exception as e:  # noqa: BLE001
        raise ApiError.internal(f"读取记忆失败: {e}")

    data = data or {}
    return success(
        MemoryLayersData(
            short_term=str(data.get("short_term", "") or ""),
            long_term=str(data.get("long_term", "") or ""),
            detailed=_detailed(data.get("detailed")),
        )
    )


# --------------------------------------------------------------------------
# 短期 / 长期摘要
# --------------------------------------------------------------------------
async def short_term(
    session_id: str = Query("default"),
    limit: int = Query(10, ge=1, le=100),
) -> ApiResponse[MemoryShortTermData]:
    """短期记忆摘要。"""
    sysm = _memory()

    async def _call():
        return await sysm.get_short_term_summary(session_id=session_id, limit=limit)

    try:
        text = await run_in_scheduler(_call, timeout=DEFAULT_TIMEOUT)
    except Exception as e:  # noqa: BLE001
        raise ApiError.internal(f"读取短期记忆失败: {e}")

    return success(
        MemoryShortTermData(session_id=session_id, summary=str(text or ""))
    )

async def long_term(
    session_id: str = Query("default"),
    query: str = Query("", description="提供时按语义检索"),
    limit: int = Query(12, ge=1, le=100),
) -> ApiResponse[MemoryLongTermData]:
    """长期记忆摘要。"""
    sysm = _memory()

    async def _call():
        return await sysm.get_long_term_summary(session_id=session_id, limit=limit)

    try:
        text = await run_in_scheduler(_call, timeout=DEFAULT_TIMEOUT)
    except Exception as e:  # noqa: BLE001
        raise ApiError.internal(f"读取长期记忆失败: {e}")

    return success(
        MemoryLongTermData(
            session_id=session_id,
            summary=str(text or ""),
            query=query,
        )
    )


# --------------------------------------------------------------------------
# 语义检索
# --------------------------------------------------------------------------
async def search(payload: MemorySearchRequest) -> ApiResponse[MemorySearchData]:
    """语义检索详细记忆。"""
    if not payload.query.strip():
        raise ApiError.bad_request("query 不能为空")

    sysm = _memory()

    async def _call():
        return await sysm.retrieve_memory(
            query=payload.query,
            session_id=payload.session_id,
            top_k=payload.top_k,
        )

    try:
        rows = await run_in_scheduler(_call, timeout=DEFAULT_TIMEOUT)
    except Exception as e:  # noqa: BLE001
        raise ApiError.internal(f"检索记忆失败: {e}")

    items = _detailed(rows)
    return success(MemorySearchData(query=payload.query, items=items, total=len(items)))


# --------------------------------------------------------------------------
# 压缩记忆
# --------------------------------------------------------------------------
async def compressed(
    session_id: str = Query("default"),
    limit: int = Query(24, ge=1, le=100),
) -> ApiResponse[MemoryCompressedListData]:
    """压缩记忆（历史对话摘要）列表。"""
    sysm = _memory()

    async def _call():
        fn = getattr(sysm.storage, "get_compressed", None)
        if not callable(fn):
            return []
        return await fn(session_id=session_id, limit=limit)  # type: ignore[union-attr]

    try:
        rows = await run_in_scheduler(_call, timeout=DEFAULT_TIMEOUT)
    except Exception as e:  # noqa: BLE001
        raise ApiError.internal(f"读取压缩记忆失败: {e}")

    items = _compressed(rows)
    return success(MemoryCompressedListData(items=items, total=len(items)))


# --------------------------------------------------------------------------
# 统计 / 衰减 / 排空 / 删除
# --------------------------------------------------------------------------
async def stats(session_id: str = Query("default")) -> ApiResponse[MemoryStatsData]:
    """记忆统计与容量。"""
    sysm = _memory()

    async def _call() -> Dict[str, Any]:
        records = 0
        storage = getattr(sysm, "storage", None)
        memories = getattr(storage, "memories", None)
        if memories is not None:
            records = len(memories)
        compressed = getattr(storage, "compressed_memories", None)
        tokens = 0
        try:
            for m in (memories or []):
                tokens += int(getattr(m, "tokens", 0) or 0)
        except Exception:  # noqa: BLE001
            pass
        return {
            "records": records,
            "compressed": len(compressed) if compressed is not None else 0,
            "tokens": tokens,
            "backend": type(storage).__name__ if storage else "",
        }

    try:
        data = await run_in_scheduler(_call, timeout=DEFAULT_TIMEOUT)
    except Exception as e:  # noqa: BLE001
        raise ApiError.internal(f"读取记忆统计失败: {e}")

    return success(
        MemoryStatsData(
            records=int(data.get("records", 0)),
            compressed=int(data.get("compressed", 0)),
            tokens_estimate=int(data.get("tokens", 0)),
            backend=str(data.get("backend", "")),
            short_term_days=int(getattr(sysm.config, "short_term_days", 2)),
        )
    )

async def decay() -> ApiResponse[MemoryDecayData]:
    """手动触发一次重要度衰减 + 超量淘汰。"""
    sysm = _memory()

    async def _call():
        await sysm.decay_now()
        return True

    try:
        await run_in_scheduler(_call, timeout=DEFAULT_TIMEOUT)
    except Exception as e:  # noqa: BLE001
        raise ApiError.internal(f"衰减失败: {e}")
    return success(MemoryDecayData(decayed=True), message="记忆衰减已执行")

async def flush(
    timeout: float = Query(5.0, ge=0.5, le=30.0),
) -> ApiResponse[MemoryFlushData]:
    """排空后台写入（退出前或需要立刻持久化时调用）。"""
    sysm = _memory()

    async def _call():
        await sysm.flush_background(timeout=timeout)
        return True

    try:
        await run_in_scheduler(_call, timeout=timeout + 10.0)
    except Exception as e:  # noqa: BLE001
        raise ApiError.internal(f"排空失败: {e}")
    return success(MemoryFlushData(flushed=True), message="记忆写入已排空")

async def delete_memory(memory_id: str) -> ApiResponse[MemoryDeleteData]:
    """删除单条记忆。"""
    sysm = _memory()

    async def _call() -> bool:
        storage = getattr(sysm, "storage", None)
        fn = getattr(storage, "delete_memory", None)
        if not callable(fn):
            return False
        await fn(memory_id)  # type: ignore[union-attr]
        return True

    try:
        ok = await run_in_scheduler(_call, timeout=DEFAULT_TIMEOUT)
    except Exception as e:  # noqa: BLE001
        raise ApiError.internal(f"删除记忆失败: {e}")

    if not ok:
        raise ApiError.internal("当前存储后端不支持删除单条记忆")
    return success(MemoryDeleteData(id=memory_id, deleted=True), message="记忆已删除")