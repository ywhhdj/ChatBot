"""compat.py —— OpenAI / Responses 协议兼容层。

给外部 Agent 客户端当模型后端用，典型调用方：

* **OpenAI Codex CLI**（0.94+）：只发 ``POST /v1/responses``，
  ``wire_api = "responses"``，要 Responses SSE 语义事件。
* **DeepSeek Harness (dsh)**：``DEEPSEEK_BASE_URL`` 指向 OpenAI 兼容端点，
  发 ``POST /v1/chat/completions``；也可改走 Anthropic 兼容端点（本层未实现）。
* 任意 OpenAI SDK / LiteLLM / OpenRouter 风格客户端。
"""
from __future__ import annotations

import json
import os
import secrets
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse

from .._common import to_thread
from ..requests import CompatChatRequest, CompatResponsesRequest

# 官方弃用名 → 现行名（api-docs.deepseek.com，2026-11）
MODEL_ALIASES: Dict[str, str] = {
    "deepseek-chat": "deepseek-flash",
    "deepseek-reasoner": "deepseek-v4-pro",
    "deepseek-v4-flash": "deepseek-flash",
    "deepseek-v4-flash-vision-exp": "deepseek-flash",
}

MAX_INPUT_ITEMS = 512
MAX_TEXT_CHARS = 400_000
MAX_TOOL_DEFS = 64


class CompatError(Exception):
    """兼容层内部错误，统一转成 OpenAI 风格 error 对象。"""

    def __init__(self, message: str, status: int = 400, kind: str = "invalid_request_error"):
        super().__init__(message)
        self.message = message
        self.status = status
        self.kind = kind


# --------------------------------------------------------------------------
# 通用小工具
# --------------------------------------------------------------------------


def _uid(prefix: str) -> str:
    return prefix + uuid.uuid4().hex[:24]


def _openai_error(message: str, status: int = 400, kind: str = "invalid_request_error") -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"message": message, "type": kind, "param": None, "code": None}},
    )


def _check_auth(request: Request) -> Optional[JSONResponse]:
    """可选 Bearer 鉴权。未设 CHATBOT_COMPAT_TOKEN 时沿用本地回环无认证约定。"""
    token = os.environ.get("CHATBOT_COMPAT_TOKEN", "").strip()
    if not token:
        return None
    header = request.headers.get("Authorization", "")
    supplied = header[7:] if header.startswith("Bearer ") else ""
    if not supplied or not secrets.compare_digest(supplied, token):
        return _openai_error("Invalid API key", 401, "invalid_api_key")
    return None


def _text_of_content(content: Any) -> str:
    """把 Chat Completions / Responses 的 content 结构归一成纯文本。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                if part.get("type") in ("input_image", "image", "input_file"):
                    continue  # 视觉/文件项不投影，见 §4.5 限制
                text = part.get("text")
                if text is not None:
                    parts.append(str(text))
        return "\n".join(p for p in parts if p)
    if isinstance(content, dict):
        return _text_of_content(content.get("text") or content.get("content"))
    return str(content)


def _usage(data: Any) -> Dict[str, int]:
    raw = data if isinstance(data, dict) else {}
    return {
        "input_tokens": int(raw.get("input_tokens") or raw.get("prompt_tokens") or 0),
        "output_tokens": int(raw.get("output_tokens") or raw.get("completion_tokens") or 0),
        "total_tokens": int(
            raw.get("total_tokens")
            or (raw.get("input_tokens") or raw.get("prompt_tokens") or 0)
            + (raw.get("output_tokens") or raw.get("completion_tokens") or 0)
        ),
    }


# --------------------------------------------------------------------------
# 模型目录与解析
# --------------------------------------------------------------------------


def _registry():
    from ...providers import factory

    reg = factory.get_registry()
    reg.refresh()
    return reg


def _catalog() -> List[Tuple[str, str, str, bool]]:
    """(provider_id, model_id, label, deprecated)，只收 llm 能力。"""
    reg = _registry()
    out: List[Tuple[str, str, str, bool]] = []
    for pid in reg.provider_ids("llm"):
        try:
            prov = reg.get("llm", pid)
        except KeyError:
            continue
        for m in prov.get("models") or []:
            if not isinstance(m, dict) or not m.get("id"):
                continue
            out.append((
                str(pid), str(m["id"]), str(m.get("label") or m["id"]),
                bool(m.get("deprecated")),
            ))
    return out


def _current_provider(reg, ids: List[str]) -> str:
    try:
        from ...config import get_config

        name = str(get_config().llm.provider or "").strip()
        if name in ids:
            return name
    except Exception:  # noqa: BLE001
        pass
    return "deepseek" if "deepseek" in ids else (ids[0] if ids else "")


def _resolve_model(model: str) -> Tuple[str, str, str]:
    """返回 (provider_id, 真实 model_id, 回显给客户端的 model)。

    外部客户端可能写旧名、自定义别名或随便一个 id；只要落在 Registry 白名单
    就用对应 provider，否则退到当前选中 provider 的首个可用模型，**不切全局
    流量**（本层是请求级适配，不调用 provider_manager.switch）。
    """
    reg = _registry()
    ids = list(reg.provider_ids("llm") or [])
    if not ids:
        raise CompatError("未配置任何 llm provider", 503, "api_error")

    target = MODEL_ALIASES.get(model, model)
    for pid, mid, _label, deprecated in _catalog():
        if mid == target:
            real = target
            if deprecated:
                try:
                    prov = reg.get("llm", pid)
                    for m in prov.get("models") or []:
                        if isinstance(m, dict) and m.get("id") == target:
                            real = str(m.get("alias_of") or target)
                            break
                except KeyError:
                    pass
            return pid, real, model or mid

    pid = _current_provider(reg, ids)
    first = next(
        (m for p, m, _l, dep in _catalog() if p == pid and not dep), ""
    )
    return pid, first or pid, model or first or pid


def _build_adapter(provider: str, model_id: str):
    from ...providers import factory

    return factory.create_adapter("llm", provider, model_id=model_id)


# --------------------------------------------------------------------------
# 请求投影
# --------------------------------------------------------------------------


def _project_input(raw: Any, instructions: str) -> List[Dict[str, Any]]:
    """Responses ``input`` → Chat Completions ``messages``。"""
    messages: List[Dict[str, Any]] = []
    if isinstance(instructions, str) and instructions.strip():
        messages.append({"role": "system", "content": instructions.strip()[:MAX_TEXT_CHARS]})

    if isinstance(raw, str):
        if raw.strip():
            messages.append({"role": "user", "content": raw[:MAX_TEXT_CHARS]})
        return messages
    if raw is None:
        return messages
    if not isinstance(raw, list):
        messages.append({"role": "user", "content": _text_of_content(raw)[:MAX_TEXT_CHARS]})
        return messages

    for item in raw[:MAX_INPUT_ITEMS]:
        if isinstance(item, str):
            messages.append({
                "role": "user",
                "content": item[:MAX_TEXT_CHARS]
            })
            continue
        if not isinstance(item, dict):
            continue
        typ = item.get("type")

        if typ == "reasoning":
            # 服务端内部推理项，不回灌给上游模型
            continue
        if typ == "function_call_output":
            messages.append({
                "role": "tool",
                "tool_call_id": str(item.get("call_id") or item.get("id") or ""),
                "content": _text_of_content(item.get("output"))[:MAX_TEXT_CHARS],
            })
            continue
        if typ == "function_call":
            tc = {
                "id": str(item.get("call_id") or item.get("id") or _uid("call_")),
                "type": "function",
                "function": {
                    "name": str(item.get("name") or ""),
                    "arguments": str(item.get("arguments") or "{}"),
                },
            }
            if messages and messages[-1].get("role") == "assistant" and "tool_calls" in messages[-1]:
                messages[-1]["tool_calls"].append(tc)
            else:
                messages.append({
                    "role": "assistant",
                    "content": "", "tool_calls": [tc]
                })
            continue

        role = str(item.get("role") or "user")
        if role == "developer":
            role = "system"
        if role not in ("system", "user", "assistant", "tool"):
            role = "user"
        text = _text_of_content(item.get("content"))[:MAX_TEXT_CHARS]
        if not text.strip():
            continue
        messages.append({"role": role, "content": text})
    return messages


def _normalize_tools(tools: Any) -> Optional[List[Dict[str, Any]]]:
    """Responses 扁平 function 定义 → Chat Completions ``tools`` 结构。"""
    if not isinstance(tools, list):
        return None
    out: List[Dict[str, Any]] = []
    for t in tools[:MAX_TOOL_DEFS]:
        if not isinstance(t, dict) or (t.get("type") or "function") != "function":
            # web_search / code_interpreter 等内置工具不由本层代理
            continue
        fn = t.get("function") if isinstance(t.get("function"), dict) else None
        normalized: Dict[str, Any] = {
            "name": (fn or t).get("name") or "",
            "description": (fn or t).get("description") or "",
            "parameters": (fn or t).get("parameters") or {
                "type": "object",
                "properties": {}
            },
        }
        if (fn or t).get("strict"):
            normalized["strict"] = True
        out.append({"type": "function", "function": normalized})
    return out or None


def _normalize_messages(messages: Any) -> List[Dict[str, Any]]:
    """Chat Completions 入口：把 content 结构归一，保留 tool_calls。"""
    if not isinstance(messages, list):
        return []
    out: List[Dict[str, Any]] = []
    for m in messages[:MAX_INPUT_ITEMS]:
        if not isinstance(m, dict):
            continue
        item = dict(m)
        if "content" in item and item["content"] is not None:
            item["content"] = _text_of_content(item["content"])[:MAX_TEXT_CHARS]
        out.append(item)
    return out


def _max_tokens(payload: Any) -> int:
    extra = getattr(payload, "model_extra", None) or {}
    raw = (
        extra.get("max_completion_tokens")
        or getattr(payload, "max_tokens", None)
        or getattr(payload, "max_output_tokens", None)
        or 1024
    )
    try:
        return max(1, min(int(raw), 65536))
    except (TypeError, ValueError):
        return 1024


# --------------------------------------------------------------------------
# 上游调用：openai 协议走原始响应，其它协议降级为纯文本
# --------------------------------------------------------------------------


def _fake_chat_completion(text: str, model: str) -> Dict[str, Any]:
    return {
        "id": _uid("chatcmpl-"),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": text
            },
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        },
    }


def _fake_chat_chunk(text: str, model: str, chunk_id: str) -> Dict[str, Any]:
    return {
        "id": chunk_id, 
        "object": "chat.completion.chunk",
        "created": int(time.time()), "model": model,
        "choices": [{
            "index": 0,
            "delta": {"content": text},
            "finish_reason": None
        }],
    }


async def _call_json(shim, messages, tools, temperature: float, max_tokens: int, model: str) -> Dict[str, Any]:
    if shim._protocol() == "openai":
        payload = shim._payload(messages, tools, temperature, max_tokens, stream=False)
        data = await shim._ensure_transport().request_json(
            payload, path_params=shim._path_params()
        )
        data.setdefault("id", _uid("chatcmpl-"))
        data.setdefault("object", "chat.completion")
        data.setdefault("created", int(time.time()))
        return data
    text = await shim.generate_text(messages, tools, temperature, max_tokens)
    return _fake_chat_completion(str(text or ""), model)


async def _call_stream(shim, messages, tools, temperature: float, max_tokens: int, model: str) -> AsyncGenerator[Dict[str, Any], None]:
    if shim._protocol() == "openai":
        payload = shim._payload(messages, tools, temperature, max_tokens, stream=True)
        async for data in shim._ensure_transport().stream_lines(
            payload, path_params=shim._path_params()
        ):
            yield data
        return
    chunk_id = _uid("chatcmpl-")
    async for text in shim.generate_text_stream(messages, tools, temperature, max_tokens):
        if text:
            yield _fake_chat_chunk(str(text), model, chunk_id)


# --------------------------------------------------------------------------
# Chat Completions → Responses 对象
# --------------------------------------------------------------------------


def _chat_to_response(data: Dict[str, Any], model: str, response_id: str = "") -> Dict[str, Any]:
    choices = data.get("choices") or []
    msg: Dict[str, Any] = {}
    if choices and isinstance(choices[0], dict):
        msg = choices[0].get("message") or {}
    text = _text_of_content(msg.get("content") or "")

    output: List[Dict[str, Any]] = []
    if text:
        output.append({
            "id": _uid("msg_"), 
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [{
                "type": "output_text",
                "text": text, "annotations": []
            }],
        })
    for tc in msg.get("tool_calls") or []:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") or {}
        output.append({
            "type": "function_call", 
            "id": _uid("fc_"),
            "call_id": str(tc.get("id") or _uid("call_")),
            "name": str(fn.get("name") or ""),
            "arguments": str(fn.get("arguments") or "{}"),
            "status": "completed",
        })
    return {
        "id": response_id or _uid("resp_"),
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": model,
        "output": output,
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "incomplete_details": None,
        "usage": _usage(data.get("usage")),
    }


def _sse(event_type: str, data: Dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _chat_sse(data: Dict[str, Any]) -> str:
    return "data: " + json.dumps(data, ensure_ascii=False) + "\n\n"


class _ResponsesStream:
    """维护 Responses SSE 的事件顺序与 sequence_number。"""

    def __init__(self, model: str) -> None:
        self.id = _uid("resp_")
        self.model = model
        self.created_at = int(time.time())
        self.seq = 0
        self.next_index = 0
        self.text_item_id = _uid("msg_")
        self.text_index: Optional[int] = None
        self.text_parts: List[str] = []
        self.text_opened = False
        self.text_closed = False
        self.tool_items: Dict[int, Dict[str, Any]] = {}
        self.usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0
        }

    def emit(self, typ: str, **fields: Any) -> str:
        self.seq += 1
        return _sse(typ, {
            "type": typ,
            "sequence_number": self.seq,
            **fields
        })

    def response(self, status: str, *, error: Any = None) -> Dict[str, Any]:
        output: List[Dict[str, Any]] = []
        if self.text_parts:
            output.append({
                "id": self.text_item_id, 
                "type": "message",
                "status": "completed", 
                "role": "assistant",
                "content": [{
                    "type": "output_text",
                    "text": "".join(self.text_parts),
                    "annotations": [],
                }],
            })
        for ent in sorted(self.tool_items.values(), key=lambda e: e["index"]):
            output.append({
                "type": "function_call",
                "id": ent["id"],
                "call_id": ent["call_id"], 
                "name": ent["name"],
                "arguments": "".join(ent["args"]), 
                "status": "completed",
            })
        out: Dict[str, Any] = {
            "id": self.id, "object": "response", "created_at": self.created_at,
            "status": status, "model": self.model, "output": output,
            "parallel_tool_calls": True, "tool_choice": "auto", "tools": [],
            "incomplete_details": None, "usage": dict(self.usage),
        }
        if error is not None:
            out["error"] = error
        return out


# --------------------------------------------------------------------------
# 端点
# --------------------------------------------------------------------------


def list_models(request: Request) -> Any:
    """`GET /api/v1/models` — 列出 Registry 中所有可用的 llm 模型。

    同样过可选 Bearer 鉴权：远程监听时不能让未授权调用方枚举模型目录。
    """
    denied = _check_auth(request)
    if denied is not None:
        return denied
    data = [
        {
            "id": mid, 
            "object": "model",
            "created": 0,
            "owned_by": pid,
            "label": label,
        }
        for pid, mid, label, deprecated in _catalog()
        if not deprecated
    ]
    return {
        "object": "list",
        "data": data
    }


async def chat_completions(payload: CompatChatRequest, request: Request) -> Any:
    """`POST /api/v1/chat/completions` — DeepSeek Harness / OpenAI SDK 兼容端点。"""
    denied = _check_auth(request)
    if denied is not None:
        return denied
    try:
        messages = _normalize_messages(payload.messages)
        if not messages:
            raise CompatError("messages 不能为空")
        provider, model_id, echo_model = _resolve_model(payload.model)
        shim = await to_thread(_build_adapter, provider, model_id)
        tools = _normalize_tools(payload.tools)
        max_tokens = _max_tokens(payload)

        if not payload.stream:
            return await _call_json(
                shim,
                messages,
                tools,
                payload.temperature,
                max_tokens,
                echo_model
            )

        async def gen() -> AsyncGenerator[str, None]:
            chunk_id = _uid("chatcmpl-")
            try:
                async for data in _call_stream(
                    shim, messages, tools, payload.temperature, max_tokens, echo_model
                ):
                    data.setdefault("id", chunk_id)
                    data.setdefault("object", "chat.completion.chunk")
                    data.setdefault("created", int(time.time()))
                    yield _chat_sse(data)
            except Exception:  # noqa: BLE001
                yield _chat_sse({
                    "id": chunk_id, 
                    "object": "chat.completion.chunk",
                    "created": int(time.time()), 
                    "model": echo_model,
                    "choices": [], 
                    "error": {"message": "上游模型请求失败"},
                })
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            gen(), media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no"
            },
        )
    except CompatError as exc:
        return _openai_error(exc.message, exc.status, exc.kind)
    except Exception:  # noqa: BLE001
        return _openai_error("上游模型请求失败", 502, "api_error")



async def responses(payload: CompatResponsesRequest, request: Request) -> Any:
    """`POST /api/v1/responses` — Codex CLI 0.94+ 专用 Responses API 兼容端点。"""
    denied = _check_auth(request)
    if denied is not None:
        return denied
    try:
        messages = _project_input(payload.input, payload.instructions)
        if not messages:
            raise CompatError("input 不能为空")
        provider, model_id, echo_model = _resolve_model(payload.model)
        shim = await to_thread(_build_adapter, provider, model_id)
        tools = _normalize_tools(payload.tools)
        max_tokens = _max_tokens(payload)

        if not payload.stream:
            data = await _call_json(
                shim, messages, tools, payload.temperature, max_tokens, echo_model
            )
            return _chat_to_response(data, echo_model)

        async def gen() -> AsyncGenerator[str, None]:
            st = _ResponsesStream(echo_model)
            # response.created 必须是第一帧，SDK 会强校验
            yield st.emit("response.created", response=st.response("in_progress"))
            yield st.emit("response.in_progress", response=st.response("in_progress"))
            try:
                async for data in _call_stream(
                    shim, messages, tools, payload.temperature, max_tokens, echo_model
                ):
                    if data.get("usage"):
                        st.usage = _usage(data["usage"])
                    for choice in data.get("choices") or []:
                        delta = choice.get("delta") or {}

                        text = _text_of_content(delta.get("content"))
                        if text:
                            if not st.text_opened:
                                st.text_index = st.next_index
                                st.next_index += 1
                                yield st.emit(
                                    "response.output_item.added",
                                    output_index=st.text_index,
                                    item={
                                        "id": st.text_item_id, 
                                        "type": "message",
                                        "status": "in_progress", 
                                        "role": "assistant",
                                        "content": [],
                                    },
                                )
                                yield st.emit(
                                    "response.content_part.added",
                                    item_id=st.text_item_id,
                                    output_index=st.text_index,
                                    content_index=0,
                                    part={
                                        "type": "output_text",
                                        "text": "",
                                        "annotations": []
                                    },
                                )
                                st.text_opened = True
                            st.text_parts.append(text)
                            yield st.emit(
                                "response.output_text.delta",
                                item_id=st.text_item_id,
                                output_index=st.text_index,
                                content_index=0,
                                delta=text,
                            )

                        for tc in delta.get("tool_calls") or []:
                            if not isinstance(tc, dict):
                                continue
                            idx = int(tc.get("index") or 0)
                            ent = st.tool_items.get(idx)
                            if ent is None:
                                ent = {
                                    "id": _uid("fc_"),
                                    "call_id": str(tc.get("id") or _uid("call_")),
                                    "name": "", "args": [],
                                    "index": st.next_index,
                                }
                                st.next_index += 1
                                st.tool_items[idx] = ent
                                yield st.emit(
                                    "response.output_item.added",
                                    output_index=ent["index"],
                                    item={
                                        "type": "function_call", 
                                        "id": ent["id"],
                                        "call_id": ent["call_id"],
                                        "name": "",
                                        "arguments": "", 
                                        "status": "in_progress",
                                    },
                                )
                            fn = tc.get("function") or {}
                            if fn.get("name"):
                                ent["name"] = str(fn["name"])
                            if fn.get("arguments"):
                                frag = str(fn["arguments"])
                                ent["args"].append(frag)
                                yield st.emit(
                                    "response.function_call_arguments.delta",
                                    item_id=ent["id"],
                                    output_index=ent["index"],
                                    delta=frag,
                                )

                # 关闭文本项（顺序：text.done → content_part.done → output_item.done）
                if st.text_opened and not st.text_closed:
                    full = "".join(st.text_parts)
                    yield st.emit(
                        "response.output_text.done",
                        item_id=st.text_item_id, output_index=st.text_index,
                        content_index=0, text=full,
                    )
                    yield st.emit(
                        "response.content_part.done",
                        item_id=st.text_item_id, 
                        output_index=st.text_index,
                        content_index=0,
                        part={
                            "type": "output_text",
                            "text": full,
                            "annotations": []
                        },
                    )
                    yield st.emit(
                        "response.output_item.done",
                        output_index=st.text_index,
                        item={
                            "id": st.text_item_id,
                            "type": "message",
                            "status": "completed",
                            "role": "assistant",
                            "content": [{
                                "type": "output_text",
                                "text": full,
                                "annotations": [],
                            }],
                        },
                    )
                    st.text_closed = True

                # 关闭工具项
                for ent in sorted(st.tool_items.values(), key=lambda e: e["index"]):
                    args = "".join(ent["args"])
                    yield st.emit(
                        "response.function_call_arguments.done",
                        item_id=ent["id"], output_index=ent["index"],
                        name=ent["name"], arguments=args,
                    )
                    yield st.emit(
                        "response.output_item.done",
                        output_index=ent["index"],
                        item={
                            "type": "function_call", "id": ent["id"],
                            "call_id": ent["call_id"], "name": ent["name"],
                            "arguments": args, "status": "completed",
                        },
                    )

                yield st.emit("response.completed", response=st.response("completed"))
            except Exception:  # noqa: BLE001
                err = {
                    "code": "api_error",
                    "message": "上游模型请求失败"
                }
                yield st.emit(
                    "response.failed",
                    response=st.response("failed", error=err),
                )
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            gen(), media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no"
            },
        )
    except CompatError as exc:
        return _openai_error(exc.message, exc.status, exc.kind)
    except Exception:  # noqa: BLE001
        return _openai_error("上游模型请求失败", 502, "api_error")
