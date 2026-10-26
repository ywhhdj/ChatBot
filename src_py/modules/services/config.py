"""各服务的 UI 配置描述。

`manager/service/manager.py` 里 `from ...services import ServiceId, config`
随后 `config.ObsConfig().get_ui_config_items()` —— 这个子模块在源码中缺失，
服务 UI 描述接口一调用就 ImportError。

这里提供最小可用实现：每个 Config 用 `get_ui_config_items()` 返回
一组「字段描述」，供前端渲染设置面板，不依赖真实服务是否启动。
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Type, TypeVar

from src_py.modules import runtime


class BaseServiceConfig:
    """配置基类。子类声明 `fields`，即可自动生成 UI 描述。"""

    service_id: str = ""
    name: str = ""
    enabled: bool = False

    fields: List[Dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        #设置属性
        for key, value in kwargs.items():
            setattr(self, key, value)
        if "enabled" not in kwargs:
            self.enabled = type(self).enabled
    
    def __getattr__(self, name: str) -> Any:
        return getattr(self, name)

    def get_ui_config_items(self) -> Dict[str, Any]:
        return {
            "id": self.service_id,
            "name": self.name,
            "enabled": bool(self.enabled),
            "fields": list(self.fields),
        }
    
    def to_dict(self) -> Dict[str, Any]:
        fields = {
            field["key"]: field["default"]
            for field in self.fields
        }
        return {
            "service": self.service_id,
            "name": self.name,
            "enabled": bool(self.enabled),
            **fields
        }


def _field(
    key: str,
    label: str,
    type_: str = "string",
    default: Any = "",
    description: str = "",
    options: Optional[List[str]] = None,
    **extra: Any
) -> Dict[str, Any]:
    item = {
        "key": key,
        "label": label,
        "type": type_,
        "default": default,
        "description": description,
        "options": options,
    }
    item.update(extra)
    return item


class Live2DConfig(BaseServiceConfig):
    service_id = "live2d"
    name = "Live2D"
    enabled = True
    fields = [
        _field("model_path", "模型路径", default=runtime.RuntimePath.get_models_path("resources/models/live2d/肥牛/hiyori_pro_mic.model3.json"), description="模型目录或 .model3.json 路径"),
        _field("canvas_size", "画布尺寸", type_="string", default="1200x800"),
        _field("fps", "帧率", type_="number", default=60,description="模型渲染帧率"),
        _field("enable_audio_sync", "口型同步", type_="boolean", default=True,description="是否开启口型同步"),
        _field("pipeface_model_path", "人脸检测模型路径", type_="string", default=runtime.RuntimePath.get_models_path("mediapipe/face_landmarker.task"),description="人脸检测任务模型路径"),
    ]


class ObsConfig(BaseServiceConfig):
    service_id = "obs"
    name = "OBS"
    enabled = False
    fields = [
        _field("ip", "IP 地址", default="127.0.0.1",description="OBS WebSocket 服务器 IP 地址"),
        _field("port", "端口", type_="number", default=4455,description="OBS WebSocket 端口"),
        _field("password", "WebSocket 密码", type_="password", default="",description="OBS WebSocket 密码"),
        _field("timeout", "超时(秒)", type_="number", default=10,description="OBS WebSocket 连接超时时间"),
    ]


class BrowserConfig(BaseServiceConfig):
    service_id = "browser"
    browser_type = "chrome"
    user_data_dir = ""
    profile_name = "Default"
    user_agent = ""
    viewport = {"width": 1280, "height": 800}
    name = "浏览器"
    enabled = False
    fields = [
        _field(
            "browser_type",
            "浏览器类型",
            default="chrome",
            options=["chrome", "edge", "firefox"],
            description="浏览器类型",
        ),
        _field("headless", "无头模式", type_="boolean", default=False,description="是否开启无头模式"),
        _field("cdp_url", "CDP 地址", default="",
               description="连接已运行的浏览器；留空则新建实例"),
        _field("proxy", "代理", default=""),
        _field("user_data_dir", "用户数据目录", default="",
               description="持久化 profile 目录，配合 profile_name 使用"),
        _field("profile_name", "Profile 名称", default="Default"),
        _field("user_agent", "User-Agent", default=""),
        _field("viewport", "视口", type_="object",
               default={"width": 1280, "height": 800}),
    ]


class QQBotConfig(BaseServiceConfig):
    service_id = "qqbot"
    name = "QQ 机器人"
    enabled = False
    fields = [
        _field("app_id", "AppID", default=""),
        _field("token", "Token", type_="password", default="",description="机器人 Token"),
        _field("secret", "Secret", type_="password", default="",description="机器人 Secret"),
        _field("sandbox", "沙箱环境", type_="boolean", default=True,description="是否开启沙箱环境"),
    ]

class ServiceConfig(BaseServiceConfig):
    qqbot: QQBotConfig = QQBotConfig()
    browser: BrowserConfig = BrowserConfig()
    live2d: Live2DConfig = Live2DConfig()
    obs: ObsConfig = ObsConfig()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "live2d": self.live2d.to_dict(),
            "obs": self.obs.to_dict(),
            "browser": self.browser.to_dict(),
            "qqbot": self.qqbot.to_dict(),
        }



CONFIG_CLASSES: Dict[str, Any] = {
    "live2d": Live2DConfig,
    "obs": ObsConfig,
    "browser": BrowserConfig,
    "qqbot": QQBotConfig,
}

def get_service_classes(service_id: str):
    return CONFIG_CLASSES[service_id]