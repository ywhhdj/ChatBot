from ..transports.http import HttpTransport
from ..transports.local import LocalTransport

SECRET_KEYS = {"api_key", "secret_key", "token", "access_key"}

_ENDPOINT_KEYS = {
    "base_url", "chat_path", "auth", "timeout", "max_retries",
    "transport", "runtime", "model_dir", "device", "protocol", "method",
    "language", "beam_size", "sample_rate", "lang", "languages", "dtype",
}


class _ShimBase:
    capability: str = ""

    def __init__(self, registry, provider_id, secrets=None, **init_params):
        self.registry = registry
        self.provider_id = provider_id
        self.secrets = secrets or {}

        self.init_params = dict(init_params)
        self.model_id = self.init_params.pop("model", None)

        endpoint_overrides = {
            k: self.init_params.pop(k)
            for k in list(self.init_params)
            if k in _ENDPOINT_KEYS and self.init_params[k] is not None
        }

        self._cfg = registry.merged(self.capability, provider_id, self.model_id)
        self._cfg["endpoint"].update(endpoint_overrides)
        self._http = None
        self._local = None

    def _ensure_transport(self):
        if self._http is None:
            ep = self._cfg["endpoint"]
            self._http = HttpTransport(ep.get("timeout", 60.0))
            self._local = LocalTransport()
        return self._http, self._local

    def close(self):
        if self._http is not None:
            try:
                self._http.close()
            except Exception:
                pass
            self._http = None
        if self._local is not None:
            try:
                self._local.close()
            except Exception:
                pass
            self._local = None