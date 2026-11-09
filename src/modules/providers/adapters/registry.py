"""供应商配置 Registry（单一配置权威源）。
resources/config/providers/
├── models/<capability>.json     provider 定义：{provider_id: {...}}
├── schemas/<capability>.json   能力级参数默认值：{schema_version, capability, params}
└── tags.json                   标签字典（允许为空 / 未就绪）
"""
from __future__ import annotations

import json
import os
import re
import threading
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_ENV = re.compile(r"\$\{([^}]+)\}")

#: 能力白名单
CAPABILITIES = ("llm", "tts", "asr", "ocr" "image")

#: 根对象里不属于 provider 的保留键
_META_KEYS = frozenset({"schema_version", "capability", "description", "$schema"})

#: endpoint 连接参数（不进入请求 payload）
ENDPOINT_KEYS = frozenset({
    "base_url", "chat_path", "auth", "timeout", "max_retries",
    "transport", "runtime", "model_dir", "device", "protocol", "method",
    "headers",
    # 非 chat 能力专用路径
    "speech_path", "synthesize_path",   # TTS
    "image_path",                       # 图像生成（OpenAI/Qwen/Stability）
    "prompt_path",                      # ComfyUI
    "grounding_path",                   # 视觉定位
    # 流式
    "websocket_url", 
    "stream_transport",
    "first_chunk_timeout_ms",
    "first_result_timeout_ms",
})

#: 任何配置里出现这些名字都视为凭据，不进入普通配置快照
SECRET_KEYS = frozenset({
    "api_key",
    "secret_key",
    "token",
    "access_key",
    "secret",
    "password"
})


def _expand(v: Any, missing: set) -> Any:
    """展开 ``${VAR}``。未设置的变量保留占位，调用方可据此判定配置不可用。"""
    if isinstance(v, str):
        def _sub(m: "re.Match[str]") -> str:
            name = m.group(1)
            value = os.environ.get(name)
            if value:
                return value
            missing.add(name)
            return m.group(0)
        return _ENV.sub(_sub, v)
    if isinstance(v, list):
        return [_expand(x, missing) for x in v]
    if isinstance(v, dict):
        return {k: _expand(x, missing) for k, x in v.items()}
    return v


def _deep_merge(dst: dict, src: dict) -> None:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = deepcopy(v)


def endpoint_problems(endpoint: Dict[str, Any]) -> List[str]:
    """检查合并后的 endpoint 能否发起调用。供 spec 与 factory 共用。"""
    ep = endpoint or {}
    problems: List[str] = []
    if "${" in str(ep.get("base_url", "")) or "${" in str(ep.get("model_dir", "")):
        problems.append("存在未解析的 ${ENV} 占位符")
    transport = ep.get("transport")
    if transport == "http" and not ep.get("base_url"):
        problems.append("http endpoint 缺少 base_url")
    if transport == "local" and not ep.get("runtime"):
        problems.append("local endpoint 缺少 runtime")
    return problems


def _param_defaults(params: Dict[str, Any]) -> Dict[str, Any]:
    """参数描述符 → 默认值。兼容 ``{"default": ...}`` 与裸值两种写法。"""
    out: Dict[str, Any] = {}
    for name, spec in (params or {}).items():
        if isinstance(spec, dict) and "default" in spec:
            value = spec["default"]
            if value is not None:
                out[name] = deepcopy(value)
        elif not isinstance(spec, dict):
            out[name] = deepcopy(spec)
    return out


@dataclass(frozen=True)
class ProviderSpec:
    """一次解析后的供应商快照。shim / manager / API 都消费它，不再各读各的 JSON。"""

    capability: str
    provider_id: str
    model_id: Optional[str]
    endpoint: Dict[str, Any]
    params: Dict[str, Any]
    defaults: Dict[str, Any]
    meta: Dict[str, Any]
    models: Tuple[Dict[str, Any], ...]
    missing_env: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()

    @property
    def available(self) -> bool:
        """配置是否足以发起一次调用。缺凭据不算不可用（可能由调用方覆盖）。"""
        return not endpoint_problems(self.endpoint)

    @property
    def deployment(self) -> str:
        return str((self.meta or {}).get("deployment") or "")

    @property
    def label(self) -> str:
        return str((self.meta or {}).get("label") or self.provider_id)

    def model_ids(self) -> List[str]:
        return [str(m.get("id")) for m in self.models if m.get("id")]

    def flat(self, *, include_secrets: bool = False) -> Dict[str, Any]:
        """展平成 shim / entity 的 kwargs。

        ``include_secrets=False`` 时凭据字段以 ``None`` 占位，API 层可直接
        对外返回而不会泄漏环境变量；真正创建适配器时才取真值。
        """
        flat: Dict[str, Any] = {k: deepcopy(v) for k, v in self.endpoint.items() if k in ENDPOINT_KEYS}
        for k, v in self.defaults.items():
            if k not in flat:
                flat[k] = deepcopy(v)
        if self.model_id:
            flat["model"] = self.model_id

        auth = (self.endpoint.get("auth") or {})
        field_name = auth.get("field")
        if field_name:
            if include_secrets:
                flat[field_name] = os.environ.get(self.secret_env_key()) or None
            else:
                flat[field_name] = None
        return flat

    def secret_env_key(self) -> str:
        auth = (self.endpoint.get("auth") or {})
        field_name = str(auth.get("field") or "api_key")
        return f"{self.provider_id.upper()}_{field_name.upper()}"
    
    @property
    def download(self) -> Dict[str, Any]:
        raw = self.endpoint.get("download") or {}
        return dict(raw) if isinstance(raw, dict) else {}

    def ui_form(self) -> Dict[str, Any]:
        """按 scope 分组输出表单 schema，前端可直接渲染。"""
        by_scope: Dict[str, List[Dict[str, Any]]] = {}
        for name, desc in (self.params or {}).items():
            if isinstance(desc, dict):
                d = desc
            else:
                d = {"type": "string", "default": desc}
            if d.get("hidden"):
                continue
            scope = str(d.get("scope") or "request")
            item: Dict[str, Any] = {
                "name": name,
                "label": d.get("label") or name,
                "type": d.get("type", "string"),
                "default": deepcopy(d.get("default")),
                "required": bool(d.get("required")),
                "scope": scope,
                "description": d.get("description"),
            }
            for k in ("enum", "min", "max", "step", "ui", "items"):
                if k in d:
                    item[k] = deepcopy(d[k])
            by_scope.setdefault(scope, []).append(item)

        titles = {"init": "初始化", "connection": "连接", "request": "请求参数"}
        sections = [
            {"scope": s, "title": titles[s], "fields": by_scope[s]}
            for s in ("init", "connection", "request")
            if by_scope.get(s)
        ]
        return {"sections": sections}

    def describe(self) -> Dict[str, Any]:
        download = self.download
        download_meta: Optional[Dict[str, Any]] = None
        if download:
            download_meta = {
                "needed": True,
                "provider": download.get("provider") or "",
                "files": list(download.get("files") or []),
                "urls": deepcopy(download.get("urls") or {}),
                "target_dir": download.get("target_dir") or self.endpoint.get("model_dir") or "",
                "size_mb": download.get("size_mb"),
                "license": download.get("license"),
                "source": download.get("source"),
                "docs_url": download.get("docs_url"),
            }
        return {
            "capability": self.capability,
            "name": self.provider_id,
            "label": self.label,
            "meta": deepcopy(self.meta),
            "deployment": self.deployment,
            "transport": self.endpoint.get("transport"),
            "protocol": self.endpoint.get("protocol") or "",
            "runtime": self.endpoint.get("runtime") or "",
            "models": [deepcopy(m) for m in self.models],
            "selected_model": self.model_id,
            "params": deepcopy(self.params),
            "ui": self.ui_form(),
            "download": download_meta,
            "available": self.available,
            "missing_env": list(self.missing_env),
            "warnings": list(self.warnings),
        }


class Registry:
    """只读配置仓库：加载 → 合并 schema → 展开环境变量 → 缓存。"""

    def __init__(self, config_dir: Optional[str] = None) -> None:
        self.dir = Path(config_dir) if config_dir else _default_config_dir()
        self.schemas: Dict[str, Dict[str, Any]] = {}
        self.providers: Dict[str, Dict[str, Any]] = {}
        self.warnings: List[str] = []
        self._lock = threading.RLock()
        self._cache: Dict[Tuple[str, str, Optional[str]], ProviderSpec] = {}
        self._signature: str = ""
        self._env_names: Tuple[str, ...] = ()
        self.reload()

    # ---------- 加载 ----------

    def _json_files(self, directory: Path) -> List[Path]:
        if not directory.is_dir():
            return []
        return sorted(p for p in directory.glob("*.json") if p.is_file())

    def _read_json(self, path: Path) -> Optional[Dict[str, Any]]:
        try:
            raw = path.read_text("utf-8-sig").strip()
            if not raw:
                return None  # tags.json 等占位文件：跳过而不是抛 JSONDecodeError
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except Exception as exc:  # noqa: BLE001
            self.warnings.append(f"{path.name}: {type(exc).__name__}: {exc}")
            return None

    def reload(self) -> None:
        """重新扫描目录。文件 mtime/size 没变时 ``refresh()`` 不会触发它。"""
        with self._lock:
            self.warnings = []
            schemas: Dict[str, Dict[str, Any]] = {}
            providers: Dict[str, Dict[str, Any]] = {}

            for path in self._json_files(self.dir / "schemas"):
                data = self._read_json(path)
                if data:
                    schemas[path.stem] = data
            # <root>/providers//models/<capability>.json
            for path in self._json_files(self.dir /  "models"):
                data = self._read_json(path)
                if data:
                    providers[path.stem] = data

            self.schemas = schemas
            self.providers = providers
            # 配置里的 ${ENV} 占位符：变量从"未设置"变为"已设置"时也必须
            # 触发 reload，否则缓存的 spec.missing_env 永远是旧结论，
            # describe() 会一直把"已配好凭据"报成"配置不可用"。
            try:
                self._env_names = tuple(sorted(set(
                    _ENV.findall(json.dumps(providers, ensure_ascii=False))
                )))
            except Exception:  # noqa: BLE001
                self._env_names = ()
            self._cache.clear()
            self._signature = self._compute_signature()
            if not providers:
                self.warnings.append(
                    f"未在 {self.dir} 下找到 models/*.json 或 providers/*.json"
                )

    def _compute_signature(self) -> str:
        parts: List[str] = []
        for sub in ("models", "providers", "schemas"):
            for p in self._json_files(self.dir / sub):
                try:
                    st = p.stat()
                    parts.append(f"{p.name}:{st.st_mtime_ns}:{st.st_size}")
                except OSError:
                    continue
        # 只记"是否设置"，绝不把环境变量的值写进签名
        parts.append("env:" + "|".join(
            f"{name}={1 if os.environ.get(name) else 0}"
            for name in self._env_names
        ))
        return "|".join(parts)

    def refresh(self) -> bool:
        """配置热更新。只有文件签名变化才重新解析，返回是否发生了重载。"""
        with self._lock:
            if self._compute_signature() == self._signature:
                return False
            self.reload()
            return True

    # ---------- 查询 ----------

    def capabilities(self) -> List[str]:
        return [c for c in CAPABILITIES if self.providers.get(c)]

    def provider_ids(self, capability: str) -> List[str]:
        data = self.providers.get(str(capability), {}) or {}
        return [k for k in data if k not in _META_KEYS and isinstance(data[k], dict)]

    def get(self, capability: str, provider_id: str) -> Dict[str, Any]:
        try:
            return deepcopy(self.providers[capability][provider_id])
        except KeyError as exc:
            raise KeyError(
                f"provider not found: {capability}/{provider_id}"
            ) from exc

    def spec(
        self,
        capability: str,
        provider_id: str,
        model_id: Optional[str] = None,
    ) -> ProviderSpec:
        key = (str(capability), str(provider_id), model_id or None)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                return cached
            built = self._build(*key)
            self._cache[key] = built
            return built

    def _build(
        self, capability: str, provider_id: str, model_id: Optional[str]
    ) -> ProviderSpec:
        prov = self.get(capability, provider_id)
        warnings: List[str] = []

        # 1) 参数描述符：能力级 schema → provider → 选中模型
        params: Dict[str, Any] = deepcopy(
            (self.schemas.get(capability) or {}).get("params", {}) or {}
        )
        _deep_merge(params, prov.get("params", {}) or {})

        models = tuple(
            m for m in (prov.get("models") or []) if isinstance(m, dict) and m.get("id")
        )
        selected = None
        if model_id:
            selected = next((m for m in models if m.get("id") == model_id), None)
            if selected is None:
                warnings.append(
                    f"model {model_id} 不在 {provider_id} 的模型清单中，已回退默认模型"
                )
        if selected is None and models:
            selected = models[0]
        if selected is not None:
            _deep_merge(params, selected.get("params", {}) or {})

        # 2) endpoint / meta 展开环境变量
        missing: set = set()
        endpoint = _expand(prov.get("endpoint", {}) or {}, missing)
        meta = _expand(prov.get("meta", {}) or {}, missing)

        # 本地 model_dir 常写 ${MODEL_ROOT}/xxx。未设置时保留占位会让运行时
        # 去加载一个字面量路径；清空后由 runtime 回退到 model_size / 默认模型，
        # 配置缺环境变量只降级为告警，不至于让整个能力不可用。
        if "${" in str(endpoint.get("model_dir") or ""):
            warnings.append(
                f"{provider_id} 的 model_dir 含未解析环境变量，已回退运行时默认模型路径"
            )
            endpoint["model_dir"] = ""

        # 3) 配置体检（与 resources/schemas/providers.schema.json 的规则一致）
        transport = endpoint.get("transport")
        if meta.get("deployment") == "cloud" and transport != "http":
            warnings.append("deployment=cloud 要求 endpoint.transport=http")
        if transport == "http" and not endpoint.get("base_url"):
            warnings.append("http endpoint 缺少 base_url")
        if transport == "local" and not endpoint.get("runtime"):
            warnings.append("local endpoint 缺少 runtime")
        if not isinstance(endpoint.get("auth"), (dict, type(None))):
            warnings.append("endpoint.auth 必须是对象")

        built = ProviderSpec(
            capability=capability,
            provider_id=provider_id,
            model_id=str(selected.get("id")) if selected else None,
            endpoint=endpoint,
            params=params,
            defaults=_param_defaults(params),
            meta=meta,
            models=models,
            missing_env=tuple(sorted(missing)),
            warnings=tuple(warnings),
        )
        return built

    def flat_config(
        self,
        capability: str,
        provider_id: str,
        model_id: Optional[str] = None,
        *,
        include_secrets: bool = False,
    ) -> Optional[Dict[str, Any]]:
        try:
            return self.spec(capability, provider_id, model_id).flat(
                include_secrets=include_secrets
            )
        except KeyError:
            return None

    def merged(
        self, capability: str, provider_id: str, model_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """兼容旧调用方：返回融合后的 dict（含 selected_model / params / meta）。"""
        s = self.spec(capability, provider_id, model_id)
        return {
            "endpoint": deepcopy(s.endpoint),
            "params": deepcopy(s.params),
            "meta": deepcopy(s.meta),
            "models": [deepcopy(m) for m in s.models],
            "selected_model": next(
                (deepcopy(m) for m in s.models if m.get("id") == s.model_id), None
            ),
            "missing_env": list(s.missing_env),
            "warnings": list(s.warnings),
        }


def _default_config_dir() -> Path:
    env = os.environ.get("PIPELINE_CONFIG_DIR")
    if env:
        return Path(env)
    try:
        from ...runtime import StandardPaths  # modules.runtime
        return Path(StandardPaths.get_resources_dir()) / "config" / "providers"
    except Exception:  # noqa: BLE001 - 允许单独 import registry 做离线校验
        return Path("resources/config/providers")


__all__ = [
    "Registry",
    "ProviderSpec",
    "CAPABILITIES",
    "ENDPOINT_KEYS",
    "SECRET_KEYS",
]
