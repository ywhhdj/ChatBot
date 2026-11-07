import json
from typing import Dict, Optional

from .base import _ShimBase


class LLMShim(_ShimBase):
    capability = "llm"

    def initialize_client(self):
        self._ensure_transport()
        return self

    def _payload(self, messages, tools=None, temperature=0.7, max_tokens=1024, stream=False):
        p = {
            "messages": messages,
            "stream": stream,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            p["tools"] = tools
            p["tool_choice"] = "auto"
        return p

    def _get_chunk_parser(self, protocol: str):
        return {
            "ollama": self._parse_ollama_chunk,
            "deepseek": self._parse_openai_chunk,
            "chatgpt": self._parse_openai_chunk,
        }.get(protocol, self._parse_generic_chunk)

    def _parse_openai_chunk(self, d: Dict) -> Optional[str]:
        if "choices" in d and d["choices"]:
            return d["choices"][0].get("delta", {}).get("content")
        return None

    def _parse_ollama_chunk(self, d: Dict) -> Optional[str]:
        return d.get("message", {}).get("content")

    def _parse_generic_chunk(self, d: Dict) -> Optional[str]:
        for f in ("content", "text", "message", "delta"):
            if f in d:
                v = d[f]
                if isinstance(v, str):
                    return v
                if isinstance(v, dict):
                    return v.get("content") or v.get("text")
        return None

    async def generate_text_stream(self, messages, tools=None, temperature=0.7, max_tokens=1024):
        http, local = self._ensure_transport()
        ep = self._cfg["endpoint"]
        payload = self._payload(messages, tools, temperature, max_tokens, True)
        if ep.get("transport") == "local":
            async for c in local.infer(ep, payload):
                yield c
            return
        parser = self._get_chunk_parser(ep.get("protocol", "openai"))
        async for line in http.stream(ep, payload, self.secrets, stream_type="line"):
            if line.startswith("data: "):
                line = line[6:].strip()
            if line == "[DONE]":
                break
            try:
                text = parser(json.loads(line))
                if text:
                    yield text
            except json.JSONDecodeError:
                continue

    async def generate_text(self, messages, tools=None, temperature=0.7, max_tokens=1024):
        http, local = self._ensure_transport()
        ep = self._cfg["endpoint"]
        payload = self._payload(messages, tools, temperature, max_tokens, False)
        if ep.get("transport") == "local":
            return await local.infer(ep, payload)
        data = await http.request(ep, payload, self.secrets)
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")

    def get_params(self):
        return dict(self._cfg.get("params", {}))

    def close(self):
        super().close()