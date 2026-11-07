from ..runtimes import RUNTIME_REGISTRY


class LocalTransport:
    def __init__(self):
        self._instances = {}
        self._closed = False

    def _get(self, endpoint):
        if self._closed:
            self._closed = False
        key = (endpoint["runtime"], endpoint.get("model_dir", ""))
        if key not in self._instances:
            cls = RUNTIME_REGISTRY[endpoint["runtime"]]
            self._instances[key] = cls(endpoint)
        return self._instances[key]

    async def infer(self, endpoint, payload):
        return await self._get(endpoint).infer(payload)

    def close(self):
        if self._closed:
            return
        for rt in list(self._instances.values()):
            try:
                rt.close()
            except Exception:
                pass
        self._instances.clear()
        self._closed = True