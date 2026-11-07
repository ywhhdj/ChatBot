from typing import Literal

from .....utils import http


class HttpTransport:
    def __init__(self, timeout=60.0):
        self.client = http.create_httpx_async_client(timeout=timeout, follow_redirects=True)

    def _headers(self, endpoint, secrets):
        headers = dict(endpoint.get("headers", {}))
        auth = endpoint.get("auth", {})
        t = auth.get("type", "none")
        if t == "bearer":
            key = secrets.get(auth.get("field", "api_key"))
            if key:
                headers[auth["header"]] = auth.get("prefix", "") + key
        elif t == "header":
            key = secrets.get(auth.get("field", "api_key"))
            if key:
                headers[auth["header"]] = key
        return headers

    async def request(self, endpoint, payload, secrets=None):
        url = endpoint["base_url"].rstrip("/") + endpoint.get("chat_path", "")
        headers = self._headers(endpoint, secrets or {})
        return await http.async_post(url, data=payload, headers=headers, client=self.client)

    async def stream(self, endpoint, payload, secrets=None, stream_type: Literal["line", "byte"] = "byte"):
        url = endpoint["base_url"].rstrip("/") + endpoint.get("chat_path", "")
        headers = self._headers(endpoint, secrets or {})
        method = endpoint.get("method", "POST")
        if self.client is None:
            self.client=http.create_httpx_async_client()
        async with self.client.stream(method, url, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            if stream_type == "line":
                async for line in resp.aiter_lines():
                    if line:
                        yield line.strip()
            else:
                async for chunk in resp.aiter_bytes():
                    if chunk:
                        yield chunk

    def close(self):
        """同步 best-effort 关闭。不阻塞调用方。"""
        client = self.client
        self.client = None
        if client is None:
            return
        try:
            import asyncio
            asyncio.get_running_loop()
        except RuntimeError:
            try:
                asyncio.run(client.aclose())
            except Exception:
                pass
            return
        # 有运行中 loop：不阻塞当前线程，丢给后台
        try:
            import threading
            threading.Thread(target=lambda: asyncio.run(client.aclose()), daemon=True).start()
        except Exception:
            pass