"""Shim 公共基类：把 Registry 快照变成统一的供应商接口"""
from __future__ import annotations

from typing import Any, Dict, Optional

from ...registry import ENDPOINT_KEYS, SECRET_KEYS, ProviderSpec
from ..transports.http import HttpTransport
from ..transports.local import LocalTransport

__all__ = ["SECRET_KEYS", "ENDPOINT_KEYS", "_ShimBase"]


class _ShimBase:
    capability: str = ""

    def __init__(
        self,
        spec: ProviderSpec,
        secrets: Optional[Dict[str, Any]] = None,
        endpoint_overrides: Optional[Dict[str, Any]] = None,
        **init_params: Any,
    ) -> None:
        self.spec = spec
        self.provider_id = spec.provider_id
        self.model_id = spec.model_id
        self.secrets: Dict[str, Any] = dict(secrets or {})

        self.endpoint: Dict[str, Any] = dict(spec.endpoint)
        for k, v in (endpoint_overrides or {}).items():
            if k in ENDPOINT_KEYS and v is not None:
                self.endpoint[k] = v

        auth_field = str((self.endpoint.get("auth") or {}).get("field") or "")
        self._secret_keys = set(SECRET_KEYS)
        if auth_field:
            self._secret_keys.add(auth_field)

        # 请求参数 = 配置默认值 + 调用方覆盖；连接字段与凭据绝不进入 payload
        self.params = dict(spec.defaults)
        for k, v in init_params.items():
            if k in ENDPOINT_KEYS or k in self._secret_keys or k in ("model", "model_id"):
                continue
            if v is not None:
                self.params[k] = v
        
        # 记录 scope=="init" 的参数名：它们留在 self.params 供 initialize 使用，
        # 但不进入每次请求的 payload（AIVIS 的 model_uuid / ASR 的 model_size 等）
        self._init_scope_keys = {
            k for k, desc in (spec.params or {}).items()
            if isinstance(desc, dict) and desc.get("scope") == "init"
        }

        self.init_params: Dict[str, Any] = dict(self.params)
        self._http: Optional[HttpTransport] = None
        self._local: Optional[LocalTransport] = None
        self._closed = False
        self.usage: Dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "calls": 0,
        }

    # ---------- 传输 ----------

    def _ensure_transport(self) -> HttpTransport:
        if self._http is None:
            if self._closed:
                raise RuntimeError(f"{self.capability}/{self.provider_id} 适配器已关闭")
            self._http = HttpTransport(self.endpoint, self.secrets)
        return self._http

    def _ensure_local(self) -> LocalTransport:
        if self._local is None:
            self._local = LocalTransport()
        return self._local

    # ---------- 参数 / 计量 ----------

    def request_params(self, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """构造本次请求的参数，过滤掉连接字段、凭据与空值。"""
        out = {k: v for k, v in self.params.items() if k not in self._init_scope_keys}
        for k, v in (extra or {}).items():
            if k in ENDPOINT_KEYS or k in self._secret_keys or v is None:
                continue
            out[k] = v
        return out

    def _record_usage(self, data: Any) -> None:
        """累计真实 token 用量（供应商返回 usage 时）。"""
        if not isinstance(data, dict):
            return
        usage = data.get("usage") or data.get("token_usage") or {}
        if not isinstance(usage, dict):
            return
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage.get(key)
            if isinstance(value, (int, float)):
                self.usage[key] += int(value)
        self.usage["calls"] += 1

    def get_usage(self) -> Dict[str, int]:
        return dict(self.usage)

    def get_params(self) -> Dict[str, Any]:
        return dict(self.params)

    def initialize_client(self, **kwargs: Any) -> "_ShimBase":
        """预建连接（可选）。HTTP client 由连接池按 loop 复用，这里不产生网络请求。"""
        for key, value in kwargs.items():
            if value is None:
                continue
            if key in ENDPOINT_KEYS:
                self.endpoint[key] = value
            elif key in self._secret_keys:
                self.secrets[key] = value
            elif key not in ("model", "model_id"):
                self.params[key] = value
        auth_field = str((self.endpoint.get("auth") or {}).get("field") or "")
        if auth_field:
            self._secret_keys.add(auth_field)
            if auth_field in self.params:
                self.secrets[auth_field] = self.params.pop(auth_field)
        self.init_params = dict(self.params)
        if str(self.endpoint.get("transport") or "http").lower() == "http":
            if self._http is None:
                self._ensure_transport()
            else:
                # 二次初始化（配置热更新 / app.conf 覆盖）必须把新 endpoint
                # 与凭据同步到传输层，否则请求仍打在旧的 base_url 上。
                self._http.sync(self.endpoint, self.secrets)
        return self

    # ---------- 生命周期 ----------

    def close(self) -> None:
        """幂等释放。HTTP client 归连接池管，不在 shim 里跨 loop 关闭"""
        if self._closed:
            return
        self._closed = True
        if self._http is not None:
            self._http.close()
            self._http = None
        if self._local is not None:
            try:
                self._local.close()
            except Exception:  # noqa: BLE001
                pass
            self._local = None
