"""LLM Shim：把统一的 generate_text[_stream] 映射到各供应商协议"""
from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, List, Optional

from .base import _ShimBase

_OPENAI_ONLY = frozenset({"messages", "model", "stream", "tools", "tool_choice"})
_OLLAMA_TOP_LEVEL = frozenset({"keep_alive", "format"})


def _as_dict(message: Any) -> Dict[str, Any]:
    """兼容 dict / pydantic / dataclass / 枚举 role。httpx 只能序列化纯类型。"""
    if isinstance(message, dict):
        data = dict(message)
    else:
        dump = getattr(message, "model_dump", None) or getattr(message, "to_dict", None)
        if callable(dump):
            data = dict(dump()) # type: ignore[misc]
        else:
            data = dict(getattr(message, "__dict__", {}) or {})
    for key in ("role", "content"):
        value = data.get(key) # type: ignore[misc]
        if value is not None and not isinstance(value, (str, int, float, bool, list, dict)):
            data[key] = getattr(value, "value", str(value)) # type: ignore[misc]
    return {
        k: v for k, v in data.items()  # type: ignore[misc]
        if v is not None and k != "timestamp"
    }


class LLMShim(_ShimBase):
    capability = "llm"

    # ---------- 协议 ----------

    def _protocol(self) -> str:
        if self.endpoint.get("transport") == "local":
            return "local"
        protocol = str(self.endpoint.get("protocol") or "").lower()
        if protocol:
            return protocol
        if self.provider_id.lower() == "ollama" or "/api/chat" in str(
            self.endpoint.get("chat_path") or ""
        ):
            return "ollama"
        return "openai"
    
    def _payload_anthropic(self, messages, model, params, max_tokens, stream) -> Dict[str, Any]:
        system_text = ""
        rest = []
        for m in messages:
            if m.get("role") == "system":
                system_text += (m.get("content") or "") + "\n"
            else:
                rest.append(m)
        payload = {
            "model": model,
            "messages": rest,
            "max_tokens": int(params.pop("max_tokens", max_tokens) or max_tokens),
            "stream": stream,
        }
        if system_text.strip():
            payload["system"] = system_text.strip()
        if "temperature" in params:
            payload["temperature"] = params.pop("temperature")
        payload.update({k: v for k, v in params.items() if k not in ("max_tokens", "temperature")})
        return payload

    def _payload_gemini(self, messages, model, params, max_tokens) -> Dict[str, Any]:
        system_text = ""
        contents = []
        for m in messages:
            role = m.get("role")
            content = m.get("content") or ""
            if role == "system":
                system_text += content + "\n"
                continue
            contents.append({
                "role": "model" if role == "assistant" else "user",
                "parts": [{"text": content}],
            })
        generation_config: Dict[str, Any] = {"temperature": params.pop("temperature", 0.7)}
        mt = params.pop("max_tokens", max_tokens)
        if mt:
            generation_config["maxOutputTokens"] = int(mt)
        generation_config.update(params)
        payload: Dict[str, Any] = {"contents": contents, "generationConfig": generation_config}
        if system_text.strip():
            payload["systemInstruction"] = {"parts": [{"text": system_text.strip()}]}
        return payload

    def _payload(
        self,
        messages: List[Any],
        tools: Optional[List[Any]] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        stream: bool = False,
        extra_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        protocol = self._protocol()
        clean_messages = [_as_dict(m) for m in messages]
        model = self.model_id or self.provider_id
        overrides = {"temperature": temperature, "max_tokens": max_tokens}
        overrides.update(extra_params or {})
        params = self.request_params(overrides)

        if protocol == "anthropic":
            return self._payload_anthropic(clean_messages, model, params, max_tokens, stream)
        if protocol == "gemini":
            return self._payload_gemini(clean_messages, model, params, max_tokens)
        if protocol == "ollama":
            # /api/chat：采样参数放 options，keep_alive / format 是顶层字段
            sampling = {
                k: v for k, v in params.items()
                if k not in _OLLAMA_TOP_LEVEL and k != "max_tokens"
            }
            sampling["temperature"] = temperature
            sampling["num_predict"] = max_tokens
            payload: Dict[str, Any] = {
                "model": model,
                "messages": clean_messages,
                "stream": stream,
                "options": sampling,
            }
            for key in _OLLAMA_TOP_LEVEL:
                if key in params:
                    payload[key] = params[key]
        else:
            payload = {
                "model": model,
                "messages": clean_messages,
                "stream": stream,
                **params,
            }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        return payload

    # ---------- 响应解析 ----------

    @staticmethod
    def _parse_content(data: Dict[str, Any], protocol: str) -> str:
        if protocol == "anthropic":
            for block in data.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "text":
                    return str(block.get("text") or "")
            return ""
        if protocol == "gemini":
            candidates = data.get("candidates") or []
            if candidates:
                parts = ((candidates[0] or {}).get("content") or {}).get("parts") or []
                return "".join(str(p.get("text") or "") for p in parts if isinstance(p, dict))
            return ""
        if protocol == "ollama":
            message = data.get("message") or {}
            return str(message.get("content") or data.get("response") or "")
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0] or {}
            message = first.get("message") or {}
            if isinstance(message, dict) and message.get("content"):
                return str(message["content"])
            if first.get("text"):
                return str(first["text"])
            delta = first.get("delta") or {}
            if isinstance(delta, dict) and delta.get("content"):
                return str(delta["content"])
        for key in ("content", "text", "response", "output"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
        return ""

    @staticmethod
    def _parse_delta(data: Dict[str, Any], protocol: str) -> str:
        if protocol == "anthropic":
            if data.get("type") == "content_block_delta":
                delta = data.get("delta") or {}
                if delta.get("type") == "text_delta":
                    return str(delta.get("text") or "")
            return ""
        if protocol == "gemini":
            candidates = data.get("candidates") or []
            if candidates:
                parts = ((candidates[0] or {}).get("content") or {}).get("parts") or []
                return "".join(str(p.get("text") or "") for p in parts if isinstance(p, dict))
            return ""
        if protocol == "ollama":
            message = data.get("message") or {}
            return str(message.get("content") or data.get("response") or "")
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0] or {}
            delta = first.get("delta") or {}
            if isinstance(delta, dict) and delta.get("content"):
                return str(delta["content"])
            message = first.get("message") or {}
            if isinstance(message, dict) and message.get("content"):
                return str(message["content"])
            if first.get("text"):
                return str(first["text"])
        return LLMShim._parse_generic_delta(data)

    @staticmethod
    def _parse_generic_delta(data: Dict[str, Any]) -> str:
        for key in ("content", "text", "response"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, dict):
                return str(value.get("content") or value.get("text") or "")
        delta = data.get("delta")
        if isinstance(delta, dict):
            return str(delta.get("content") or delta.get("text") or "")
        if isinstance(delta, str):
            return delta
        return ""
    
    def _path_params(self) -> Dict[str, str]:
        protocol = self._protocol()
        model = self.model_id or self.provider_id
        if protocol == "gemini":
            return {"model": model}
        return {}

    # ---------- 调用 ----------

    async def generate_text(
        self,
        messages: List[Any],
        tools: Optional[List[Any]] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> str:
        payload = self._payload(
            messages,
            tools,
            temperature,
            max_tokens,
            stream=False, 
            extra_params=kwargs,
        )
        protocol = self._protocol()
        if protocol == "local":
            result = await self._ensure_local().infer(self.endpoint, payload)
            if isinstance(result, dict):
                self._record_usage(result)
                return self._parse_content(result, "generic")
            return str(result or "")
        data = await self._ensure_transport().request_json(
            payload,
            path_params=self._path_params()
        )
        self._record_usage(data)
        return self._parse_content(data, protocol)

    async def generate_text_stream(
        self,
        messages: List[Any],
        tools: Optional[List[Any]] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        payload = self._payload(
            messages, 
            tools,
            temperature,
            max_tokens,
            stream=True,
            extra_params=kwargs,
        )
        protocol = self._protocol()
        if protocol == "local":
            async for chunk in self._ensure_local().stream(self.endpoint, payload):
                if isinstance(chunk, dict):
                    self._record_usage(chunk)
                    text = self._parse_content(chunk, "generic")
                    if text:
                        yield text
                elif chunk:
                    yield str(chunk)
            return
        async for data in self._ensure_transport().stream_lines(
            payload,
            path_params=self._path_params()
        ):
            if data.get("usage"):
                self._record_usage(data)
            text = self._parse_delta(data, protocol)
            if text:
                yield text

    def get_params(self) -> Dict[str, Any]:
        return dict(self.params)
