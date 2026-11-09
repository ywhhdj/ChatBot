"""Image Shim: 图像生成。OpenAI 兼容 / Stability multipart / ComfyUI 异步。"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Dict

from .base import _ShimBase


class ImageShim(_ShimBase):
    capability = "image"

    def _protocol(self) -> str:
        return str(self.endpoint.get("protocol") or "openai").lower()

    async def generate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        protocol = self._protocol()
        if protocol == "stability_multipart":
            return await self._generate_stability(payload)
        if protocol == "comfyui":
            return await self._generate_comfyui(payload)
        return await self._generate_openai(payload)

    # ---------- OpenAI / Qwen 兼容 ----------

    async def _generate_openai(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        body = dict(payload)
        if self.model_id and "model" not in body:
            body["model"] = self.model_id
        data = await self._ensure_transport().request_json(body)
        return self._parse_openai_image(data)

    # ---------- Stability multipart ----------

    async def _generate_stability(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        transport = self._ensure_transport()
        body = dict(payload)
        if self.model_id and "model" not in body:
            body["model"] = self.model_id
        files = {k: (None, str(v)) for k, v in body.items() if v is not None}
        client = transport._client_or_raise()
        async with client.stream(
            "POST", transport.build_url(), files=files, headers=transport._headers()
        ) as resp:
            resp.raise_for_status()
            raw = await resp.aread()
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {"raw": data}
        return data

    # ---------- ComfyUI：提交 → 轮询 history ----------

    async def _generate_comfyui(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        workflow = payload.get("workflow_json")
        if workflow is None:
            workflow = self.request_params().get("workflow_json")
        if not workflow:
            raise ValueError("comfyui 需要 workflow_json（API 格式工作流）")
        client_id = payload.get("client_id") or str(uuid.uuid4())
        transport = self._ensure_transport()
        data = await transport.request_json({"prompt": workflow, "client_id": client_id})
        prompt_id = data.get("prompt_id")
        if not prompt_id:
            return {"error": "ComfyUI 未返回 prompt_id", "raw": data}

        history_url = f"{transport.base_url}/history/{prompt_id}"
        client = transport._client_or_raise()
        for _ in range(120):
            await asyncio.sleep(1.0)
            resp = await client.get(history_url, headers=transport._headers())
            resp.raise_for_status()
            hist = resp.json()
            entry = hist.get(prompt_id) or {}
            outputs = entry.get("outputs") or {}
            images = []
            for node in outputs.values():
                for img in (node.get("images") or []):
                    images.append({
                        "filename": img.get("filename"),
                        "subfolder": img.get("subfolder", ""),
                        "type": img.get("type", "output"),
                    })
            if images:
                return {"prompt_id": prompt_id, "images": images, "status": "success"}
            if (entry.get("status") or {}).get("completed"):
                return {"prompt_id": prompt_id, "images": [], "status": "completed"}
        return {"prompt_id": prompt_id, "images": [], "status": "timeout"}

    @staticmethod
    def _parse_openai_image(data: Dict[str, Any]) -> Dict[str, Any]:
        items = data.get("data") or []
        out = []
        for item in items:
            if isinstance(item, dict):
                out.append({"url": item.get("url"), "b64_json": item.get("b64_json")})
        return {"data": out, "raw": data}