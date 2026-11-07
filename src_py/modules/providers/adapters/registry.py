# core/registry.py
import json, os, re
from pathlib import Path
from copy import deepcopy
from typing import Optional

_ENV = re.compile(r"\$\{([^}]+)\}")

def _expand(v):
    if isinstance(v, str):
        return _ENV.sub(lambda m: os.environ.get(m.group(1), ""), v)
    if isinstance(v, list):
        return [_expand(x) for x in v]
    if isinstance(v, dict):
        return {k: _expand(x) for k, x in v.items()}
    return v

def _deep_merge(dst: dict, src: dict):
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = deepcopy(v)

class Registry:
    def __init__(self, config_dir="config"):
        self.dir = Path(config_dir)
        self.schemas, self.providers = {}, {}
        for p in (self.dir / "schemas").glob("*.json"):
            self.schemas[p.stem] = json.loads(p.read_text("utf-8"))
        for p in (self.dir / "providers").glob("*.json"):
            self.providers[p.stem] = json.loads(p.read_text("utf-8"))

    def get(self, capability, provider_id):
        return self.providers[capability][provider_id]

    def merged(self, capability: str, provider_id: str, model_id: Optional[str] = None):
        prov = deepcopy(self.get(capability, provider_id))
        params = deepcopy(self.schemas.get(capability, {}).get("params", {}))
        _deep_merge(params, prov.get("params", {}))
        model = None
        for m in prov.get("models", []):
            if m["id"] == model_id:
                model = m
                _deep_merge(params, m.get("params", {}))
                break
        prov["params"] = params
        prov["selected_model"] = model
        prov["endpoint"] = _expand(prov["endpoint"])
        prov["meta"] = _expand(prov["meta"])
        return prov