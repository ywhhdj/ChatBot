"""供应商适配器工厂：Registry 快照 → Shim 实例。

调用链（唯一入口）：:

    entity.LLM.initialize_provider(provider, **flat)
        └─ factory.create_adapter("llm", provider, **flat)
             ├─ Registry.spec()       一次解析、缓存
             ├─ 拆分 secrets / endpoint 覆盖 / 请求参数
             └─ LLMShim(spec=..., secrets=..., **init_params)

设计要点
────────
* 不再在 shim 里二次读 Registry：spec 只解析一次，切换 provider 时旧配置的
  deepcopy 与环境变量展开不会重复发生。
* 凭据只在 ``create_adapter`` 内部流转，绝不写回 Registry / 配置快照。
* ``PIPELINE_CONFIG_DIR`` 可覆盖目录；默认由 ``runtime.StandardPaths`` 定位到
  ``<app_root>/resources/config/providers``，不再依赖进程 CWD。
"""
from __future__ import annotations

import os
import threading
from typing import Any, Dict, Optional, Tuple, Type

from .adapters.registry import (
    ENDPOINT_KEYS,
    SECRET_KEYS,
    Registry,
    _default_config_dir,
    endpoint_problems,
)
from .adapters.adapters.shim import ASRShim, LLMShim, OCRShim, TTSShim,ImageShim

_registry: Optional[Registry] = None
_registry_lock = threading.Lock()

_SHIMS: Dict[str, Type[Any]] = {
    "llm": LLMShim,
    "tts": TTSShim,
    "asr": ASRShim,
    "ocr": OCRShim,
    "image": ImageShim,
}


def get_registry() -> Registry:
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = Registry()
    return _registry


def reload_registry() -> Registry:
    """配置热更新；并发调用安全，返回当前 Registry 单例。"""
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = Registry()
        else:
            _registry.refresh() # type: ignore
    return _registry


def default_config_dir() -> str:
    return str(_default_config_dir())


def _split(
    kwargs: Dict[str, Any],
    extra_secret_keys: Optional[set] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """拆成 (secrets, endpoint_overrides, init_params)。

    ``init_params`` 里只保留请求/初始化参数，避免把 ``base_url`` 之类的
    连接字段塞进 LLM/TTS 的 JSON payload（旧实现会把它们原样发给供应商）。

    ``extra_secret_keys`` 用于容纳配置里 ``endpoint.auth.field`` 自定义的名字
    （例如 ``api-key``），否则它会被当成普通请求参数发给供应商。
    """
    secret_keys = set(SECRET_KEYS) | set(extra_secret_keys or ())
    secrets: Dict[str, Any] = {}
    endpoint: Dict[str, Any] = {}
    params: Dict[str, Any] = {}
    for key, value in kwargs.items():
        if key in secret_keys:
            if value is not None:
                secrets[key] = value
        elif key in ENDPOINT_KEYS:
            if value is not None:
                endpoint[key] = value
        elif key in ("model_id", "model"):
            continue  # 模型选择由 Registry 的 spec 决定，不进 payload
        else:
            params[key] = value
    return secrets, endpoint, params


def create_adapter(
    capability: str,
    provider: str,
    *,
    model_id: Optional[str] = None,
    **kwargs: Any,
) -> Any:
    """创建一个供应商适配器。

    ``kwargs`` 可以含：``model``（等价于 model_id）、endpoint 覆盖字段、凭据、
    请求参数默认值。三者会被拆分后分别交给 shim，不会互相污染。
    """
    cap = str(capability or "").lower()
    shim_cls = _SHIMS.get(cap)
    if shim_cls is None:
        raise ValueError(f"Unknown capability: {capability!r}，可选: {', '.join(_SHIMS)}")

    registry = get_registry()
    registry.refresh()
    selected_model = model_id or kwargs.get("model")
    spec = registry.spec(cap, str(provider), selected_model)

    # 调用方可能连 auth 描述符一起覆盖；先取出它声明的凭据字段名，
    # 保证自定义名字（如 api-key）不会被当成普通请求参数发到供应商。
    declared_auth = kwargs.get("auth")
    declared_field = ""
    if isinstance(declared_auth, dict):
        declared_field = str(declared_auth.get("field") or "")
    secrets, endpoint_overrides, init_params = _split(
        kwargs, {declared_field} if declared_field else None
    )

    # 调用方（app.conf / switch config）可能补齐了 base_url / model_dir / auth，
    # 因此必须在覆盖合并之后再判定，不能只看原始 spec。
    effective_endpoint = {
        **spec.endpoint,
        **endpoint_overrides
    }
    auth = effective_endpoint.get("auth") or {}
    field_name = str(auth.get("field") or "")
    if field_name and field_name not in secrets and field_name in init_params:
        secrets[field_name] = init_params.pop(field_name)

    # 环境变量兜底：调用方没显式传密钥时，按 <PROVIDER>_<FIELD> 读取。
    # 显式传入优先（app.conf / 前端覆盖场景）。
    spec_field = str((spec.endpoint.get("auth") or {}).get("field") or "")
    secret_env_key = (
        f"{str(provider).upper()}_{field_name.upper()}"
        if field_name and field_name != spec_field
        else spec.secret_env_key()
    )
    if field_name and field_name not in secrets:
        env_value = os.environ.get(secret_env_key)
        if env_value:
            secrets[field_name] = env_value

    problems = endpoint_problems(effective_endpoint)
    # 非匿名 HTTP 供应商缺凭据时不建实例：否则请求会一直打到 401，
    # 编排层还会按"可重试"重复烧调用次数。
    auth_kind = str(auth.get("type") or "none").lower()
    if auth_kind in ("bearer", "header", "basic") and field_name and field_name not in secrets:
        problems.append(
            f"缺少凭据 {field_name}（设置环境变量 {secret_env_key} 或在 config 中传入）"
        )
    if problems:
        raise ValueError(
            f"provider {cap}/{provider} 配置不可用: "
            + "; ".join(problems + list(spec.warnings))
            + (f"; 未设置环境变量 {', '.join(spec.missing_env)}" if spec.missing_env else "")
        )

    return shim_cls(
        spec=spec,
        secrets=secrets,
        endpoint_overrides=endpoint_overrides,
        **init_params,
    )


__all__ = ["create_adapter", "get_registry", "reload_registry", "default_config_dir"]
