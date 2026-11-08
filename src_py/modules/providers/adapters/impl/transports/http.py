"""HTTP 传输层：共享连接池、有界重试、SSE 解析、凭据隔离。

修复要点（都是会直接烧钱 / 让链路失效的问题）
──────────────────────────────────────────────
1. ``utils.http.async_post`` 内部 ``async with client`` 会**关闭传入的共享
   client**：第一次请求之后所有请求都在已关闭连接上执行。这里直接用
   ``client.post``，client 生命周期由连接池管理。
2. 旧实现每个 shim 自建 client、切换一次 provider 就重建一次连接池；
   现在按 ``(base_url, timeout, loop)`` 复用，省掉重复 TCP/TLS 握手。
3. **LLM 生成请求不是幂等的**：响应回来之后重试会造成重复计费。
   因此只对"连接尚未建立"（ConnectError / ConnectTimeout）重试，且最多
   1 次；429/5xx/ReadTimeout 一律上抛，由编排层决定是否换供应商。
4. 支持 bearer / header / basic / none 四种鉴权，密钥只放在 headers，
   不进日志、不进 payload、不进配置快照。
"""
from __future__ import annotations

import asyncio
import base64
import json
import random
import threading
from collections import OrderedDict
from typing import Any, AsyncGenerator, Dict, Optional

_MAX_POOLED_CLIENTS = 16
_CONNECT_RETRY_LIMIT = 1


class ProviderCallError(RuntimeError):
    """供应商调用失败。消息里不含任何密钥。"""

    def __init__(self, message: str, *, status: Optional[int] = None, retryable: bool = False):
        super().__init__(message)
        self.status = status
        self.retryable = retryable


class _ClientPool:
    """按 (base_url, timeout, loop) 复用 httpx.AsyncClient"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._clients: "OrderedDict[Any, Any]" = OrderedDict()
        self._meta: Dict[Any, Dict[str, Any]] = {}
        self._retired: list = []
        #: 已排入所属 loop 的 aclose 任务。停机时要 await 它们，否则
        #: "淘汰即调度、调度完就忘" 在 loop 即将退出时等于没关连接。
        self._close_tasks: set = set()

    def acquire(self, base_url: str, timeout: float) -> Any:
        import httpx  # 延迟导入：无网络依赖时仍能 import provider 层

        loop = asyncio.get_running_loop()
        key = (str(base_url), float(timeout), id(loop))
        with self._lock:
            client = self._clients.get(key)
            if client is not None and not client.is_closed:
                self._clients.move_to_end(key)
                return client
            if client is not None:
                # 已关闭的旧条目：先登记淘汰，避免字典里留死 client
                self._clients.pop(key, None)
                self._retire_locked(client, key)

            client = httpx.AsyncClient(
                timeout=httpx.Timeout(float(timeout), connect=min(float(timeout), 10.0)),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
                follow_redirects=True,
                max_redirects=3,
            )
            self._clients[key] = client
            self._meta[key] = {"loop": loop, "base_url": base_url}
            self._evict_locked()
            return client

    def _retire_locked(self, client: Any, key: Any) -> None:
        meta = self._meta.pop(key, None) or {}
        self._retired.append((client, meta.get("loop")))

    def _evict_locked(self) -> None:
        while len(self._clients) > _MAX_POOLED_CLIENTS:
            oldest, client = self._clients.popitem(last=False)
            self._retire_locked(client, oldest)
        # 调度后清空引用，避免长期运行积累 client 对象；关闭进度由
        # _close_tasks 里的 task 持有，停机时统一等待。
        pending, self._retired = self._retired, []
        for client, loop in pending:
            self._close_on_loop(client, loop)

    def _spawn_close(self, client: Any, loop: Any) -> None:
        """在 client 所属 loop 上创建 aclose 任务并登记。"""
        if client is None or getattr(client, "is_closed", False):
            return
        try:
            task = loop.create_task(client.aclose())
        except Exception:  # noqa: BLE001 - loop 正在退出，交给 OS 回收
            return
        with self._lock:
            self._close_tasks.add(task)
        task.add_done_callback(self._discard_task)

    def _discard_task(self, task: Any) -> None:
        with self._lock:
            self._close_tasks.discard(task)

    def _close_on_loop(self, client: Any, loop: Any) -> None:
        if client is None or getattr(client, "is_closed", False):
            return
        if loop is None or loop.is_closed() or not loop.is_running():
            return  # loop 已停：无法再调度，进程退出时由 OS 回收
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        try:
            if loop is running:
                self._spawn_close(client, loop)
            else:
                loop.call_soon_threadsafe(self._spawn_close, client, loop)
        except RuntimeError:  # noqa: BLE001 - loop 恰好在这瞬间关闭
            pass

    async def shutdown(self) -> None:
        current = asyncio.get_running_loop()
        with self._lock:
            pairs: list = [
                (client, (self._meta.get(key) or {}).get("loop"))
                for key, client in self._clients.items()
            ]
            retired = list(self._retired)
            tasks = list(self._close_tasks)
            self._clients.clear()
            self._meta.clear()
            self._retired.clear()
            self._close_tasks.clear()

        # 先等在途的淘汰关闭任务，避免与下面的直接 aclose 并发重入
        for task in tasks:
            try:
                await task
            except Exception:  # noqa: BLE001
                pass

        pairs.extend(retired)
        for client, loop in pairs:
            if client is None or getattr(client, "is_closed", False):
                continue
            if loop is current or loop is None:
                try:
                    await client.aclose()
                except Exception:  # noqa: BLE001
                    pass
            else:
                self._close_on_loop(client, loop)


_POOL = _ClientPool()


async def shutdown_clients() -> None:
    await _POOL.shutdown()


class HttpTransport:
    def __init__(self, endpoint: Dict[str, Any], secrets: Optional[Dict[str, Any]] = None):
        self.endpoint = dict(endpoint or {})
        self.secrets = dict(secrets or {})
        self.base_url = str(self.endpoint.get("base_url") or "").rstrip("/")
        self.path = self._resolve_path()
        self.timeout = float(self.endpoint.get("timeout") or 60.0)
        self.max_retries = int(self.endpoint.get("max_retries") or 0)
        self.method = str(self.endpoint.get("method") or "POST").upper()
        self._client = None
    
    def _resolve_path(self) -> str:
        for key in (
            "speech_path", "synthesize_path",
            "image_path", "grounding_path",
            "prompt_path",
            "chat_path",
        ):
            value = self.endpoint.get(key)
            if value:
                return str(value)
        return ""


    # ---------- 请求构造 ----------
    
    def build_url(self, path_params: Optional[Dict[str, str]] = None) -> str:
        path = self.path
        if path_params:
            try:
                path = path.format(**path_params)
            except (KeyError, IndexError):
                pass
        base = f"{self.base_url}{path}"
        auth = self.endpoint.get("auth") or {}
        if str(auth.get("type") or "").lower() == "query":
            field = str(auth.get("field") or "key")
            value = self.secrets.get(field)
            if value:
                sep = "&" if "?" in base else "?"
                base = f"{base}{sep}{field}={value}"
        return base

    @property
    def url(self) -> str:
        return self.build_url()

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        headers.update(
            {str(k): str(v) for k, v in (self.endpoint.get("headers") or {}).items()}
        )
        auth = self.endpoint.get("auth") or {}
        kind = str(auth.get("type") or "none").lower()
        field = str(auth.get("field") or "api_key")
        header = str(auth.get("header") or "Authorization")
        value = self.secrets.get(field)
        if kind == "bearer" and value:
            headers[header] = f"{auth.get('prefix', 'Bearer ')}{value}"
        elif kind == "header" and value:
            headers[header] = str(value)
        elif kind == "basic" and value:
            headers[header] = "Basic " + base64.b64encode(str(value).encode()).decode()
        return headers

    def sync(self, endpoint: Dict[str, Any], secrets: Optional[Dict[str, Any]] = None) -> None:
        """热更新连接参数"""
        self.endpoint = dict(endpoint or {})
        if secrets:
            self.secrets.update({k: v for k, v in secrets.items() if v is not None})
        self.base_url = str(self.endpoint.get("base_url") or "").rstrip("/")
        self.path = str(self.endpoint.get("chat_path") or "")
        self.timeout = float(self.endpoint.get("timeout") or 60.0)
        self.max_retries = int(self.endpoint.get("max_retries") or 0)
        self.method = str(self.endpoint.get("method") or "POST").upper()
        self._client = None

    def _client_or_raise(self):
        if not self.base_url:
            raise ProviderCallError("HTTP endpoint 未配置 base_url")
        if self._client is None or self._client.is_closed:
            self._client = _POOL.acquire(self.base_url, self.timeout)
        return self._client

    # ---------- 非流式 ----------

    async def request_json(
        self,
        payload: Optional[Dict[str, Any]] = None,
        path_params: Optional[Dict[str, str]] = None,
        method: Optional[str] = None,
    ) -> Dict[str, Any]:
        import httpx

        retries = min(self.max_retries, _CONNECT_RETRY_LIMIT)
        m = (method or self.method or "POST").upper()
        for attempt in range(retries + 1):
            try:
                client = self._client_or_raise()
                kwargs: Dict[str, Any] = {"headers": self._headers()}
                if m in ("POST", "PUT", "PATCH") and payload is not None:
                    kwargs["json"] = payload
                response = await client.request(m, self.build_url(path_params), **kwargs)
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise ProviderCallError("供应商返回的不是 JSON 对象")
                return data
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                self._client = None
                if attempt < retries:
                    await asyncio.sleep(0.2 * (2 ** attempt) + random.random() * 0.1)
                    continue
                raise ProviderCallError(
                    f"连接供应商失败: {type(exc).__name__}", retryable=True
                ) from exc
            except httpx.HTTPStatusError as exc:
                raise ProviderCallError(
                    f"供应商返回 HTTP {exc.response.status_code}",
                    status=exc.response.status_code,
                ) from exc
            except httpx.HTTPError as exc:
                raise ProviderCallError(f"供应商请求失败: {type(exc).__name__}") from exc
        raise ProviderCallError("供应商请求失败：重试次数耗尽")

    # ---------- 流式 ----------

    async def stream_lines(
        self,
        payload: Dict[str, Any],
        path_params: Optional[Dict[str, str]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """SSE JSON 流：统一处理 ``data:`` / 空行 / ``[DONE]`` / 非 JSON 心跳。"""
        import httpx

        client = self._client_or_raise()
        try:
            async with client.stream(
                self.method, 
                self.build_url(path_params), 
                json=payload, 
                headers=self._headers()
            ) as response:
                response.raise_for_status()
                async for raw in response.aiter_lines():
                    line = (raw or "").strip()
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("event:") or line.startswith("id:"):
                        continue
                    if line.startswith("data:"):
                        line = line[5:].strip()
                    if not line or line == "[DONE]":
                        if line == "[DONE]":
                            return
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(data, dict):
                        yield data
        except httpx.HTTPStatusError as exc:
            raise ProviderCallError(
                f"流式请求返回 HTTP {exc.response.status_code}",
                status=exc.response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderCallError(f"流式请求失败: {type(exc).__name__}") from exc

    async def stream_bytes(
        self, 
        payload: Dict[str, Any],
        path_params: Optional[Dict[str, str]] = None
    ) -> AsyncGenerator[bytes, None]:
        """二进制流（TTS 音频）。"""
        import httpx

        client = self._client_or_raise()
        try:
            async with client.stream(
                self.method, 
                self.build_url(path_params), 
                json=payload,
                headers=self._headers()
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk
        except httpx.HTTPStatusError as exc:
            raise ProviderCallError(
                f"音频流返回 HTTP {exc.response.status_code}",
                status=exc.response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderCallError(f"音频流失败: {type(exc).__name__}") from exc

    def close(self) -> None:
        self._client = None


__all__ = ["HttpTransport", "ProviderCallError", "shutdown_clients"]
