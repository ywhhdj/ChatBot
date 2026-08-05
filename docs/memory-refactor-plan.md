# Memory System Refactor Plan

## Goals
1. Trigger `_compress_context_and_update` by message-count threshold and return updated context.
2. Prefer short-term memory when loading from markdown/database; LLM side defaults to compressed memory.
3. On shutdown, auto compress pending context and persist compressed memory.
4. Persist both:
- compressed memory for LLM retrieval
- detailed records for user-facing tracing
5. Use thread-pool async persistence for markdown/database writes to avoid response latency spikes.
6. Keep module boundaries clear: context orchestration vs compression vs storage.

## Module Responsibilities
1. `MessageContextManager`:
- own in-memory conversation window
- trigger periodic compression by count
- add user/assistant/tool/system messages
- flush and close memory system
2. `HybridMemorySystem`:
- tokenize
- compress context and inject compressed system messages
- route reads/writes to backend
- return layered memory (`short_term`, `long_term`, `detailed`)
3. `ContextCompressor`:
- convert messages to compression prompt
- return `CompressedContext` with summary and source ids
4. `MarkDownStorage` / DB storage:
- async append/persist detail/compressed snapshots
- prioritize short-term retrieval
- support detailed query for user inspection

## Data Classification
1. Detail Memory (trace source of truth):
- full message content
- session_id, role, timestamp, source, metadata
2. Compressed Short-Term:
- compressed chunks from recent windows
- used first when building LLM context
3. Compressed Long-Term:
- older compressed chunks ranked by recency and importance
4. Retrieval Views:
- user view: detail-first
- llm view: compressed-first, optional detail supplements

## Execution Steps
1. Fix type/import/runtime errors in memory modules.
2. Rebuild storage backend with async persistence and layered files/tables.
3. Rebuild `HybridMemorySystem` orchestration:
- periodic compression
- compressed memory persistence
- layer assembly strategy
4. Update `llmContext` to use repaired APIs and close hooks.
5. Add close-time flush/compress behavior.
6. Verify syntax and key call paths.

## Acceptance Criteria
1. New messages trigger compression every configured count.
2. `get_memory_layers()` returns compressed-first memory for LLM.
3. Detailed records are queryable for user-facing history.
4. `close()` flushes pending data and does not block chat path on file writes.
5. No recursion bugs / undefined symbols / invalid imports in `llmContext` + `MemorySystem`.
