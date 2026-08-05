from .base import ServiceState
class ServiceId:
    BROWSER = "browser"
    LIVE2D = "live2d"
    OBS = "obs"
    QQBOT = "qqbot"

__all__ = [
    "ServiceId",
    "ServiceState",
]