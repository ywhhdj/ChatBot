"""各服务的 UI 配置描述。"""

from __future__ import annotations
import copy
from typing import Any, Dict, List, Optional, Type, TypeVar

from .. import runtime


class BaseServiceConfig:
    """配置基类。子类声明 `fields`，即可自动生成 UI 描述。"""

    service_id: str = ""
    name: str = ""
    enabled: bool = False

    fields: List[Dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        for field in self._resolved_fields():
            setattr(self, field["key"], copy.deepcopy(field["default"]))
        for key, value in kwargs.items():
            setattr(self, key, value)
        if "enabled" not in kwargs:
            self.enabled = type(self).enabled
    
    def __getattr__(self, name: str) -> Any:
        raise AttributeError(f"{type(self).__name__} has no attribute {name!r}")

    def _resolved_fields(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for field in self.fields:
            item = dict(field)
            default = item.get("default")
            if callable(default):
                item["default"] = default()
            out.append(item)
        return out

    def get_ui_config_items(self) -> Dict[str, Any]:
        return {
            "id": self.service_id,
            "name": self.name,
            "enabled": bool(self.enabled),
            "fields": self._resolved_fields(),
        }

    def to_dict(self) -> Dict[str, Any]:
        fields = {
            field["key"]: getattr(self, field["key"], field["default"])
            for field in self._resolved_fields()
        }
        return {
            "service": self.service_id,
            "name": self.name,
            "enabled": bool(self.enabled),
            **fields,
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
        _field("model_path", "模型路径",
               default=lambda: str(runtime.RuntimePath.get_models_path(
                   "resources/models/live2d/肥牛/hiyori_pro_mic.model3.json")),
               description="模型目录或 .model3.json 路径"),
        _field("canvas_size", "画布尺寸", type_="string", default="1200x800"),
        _field("fps", "帧率", type_="number", default=60,description="模型渲染帧率"),
        _field("enable_audio_sync", "口型同步", type_="boolean", default=True,description="是否开启口型同步"),
        _field("pipeface_model_path", "人脸检测模型路径", type_="string",
               default=lambda: str(runtime.RuntimePath.get_models_path("mediapipe/face_landmarker.task")),
               description="人脸检测任务模型路径"),
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

class PptConfig(BaseServiceConfig):
    service_id = "ppt"
    name = "PPT生成"
    enabled = True
    fields = [
        _field("default_template", "默认模板", default="consulting",
               description="consulting/marketing/academic/launch/funding"),
        _field("default_pages", "默认页数", type_="number", default=10),
        _field("output_dir", "产出目录", default="<workspace>/ppt",
               description="只读展示：由 security/workspace 统一决定，不接受自定义绝对路径"),
    ]


class ShellConfig(BaseServiceConfig):
    """受控 shell 命令服务配置。

    `output_dir` / `cwd` 不接受外部指定：一律由 security/workspace 解析，
    这里只暴露与资源限制、命令严格程度相关的开关。
    """

    service_id = "shell"
    name = "命令行"
    enabled = True
    fields = [
        _field("shell", "Shell 程序", default="",
               description="留空按系统自动选择：Windows=cmd.exe，Linux/macOS=/bin/sh"),
        _field("timeout", "单条命令超时(秒)", type_="number", default=30.0),
        _field("max_output_bytes", "输出上限(字节)", type_="number", default=65536),
        _field("allow_dangerous_commands", "放行危险命令", type_="boolean", default=False,
               description="默认 False；rm/del/format/sudo 等始终拒绝，开启需显式安全评审"),
        _field("cwd_scope", "工作目录范围", default="workspace",
               options=["workspace", "service_output"],
               description="workspace=<工作区根>；service_output=<工作区>/shell"),
    ]


class ServiceConfig(BaseServiceConfig):
    """聚合视图。配置必须是**实例属性**：类级共享可变对象会让所有
    ServiceConfig 实例共用同一份 QQBotConfig，改一处串到全部。"""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.qqbot = QQBotConfig()
        self.browser = BrowserConfig()
        self.live2d = Live2DConfig()
        self.obs = ObsConfig()
        self.ppt = PptConfig()
        self.shell = ShellConfig()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "live2d": self.live2d.to_dict(),
            "obs": self.obs.to_dict(),
            "browser": self.browser.to_dict(),
            "qqbot": self.qqbot.to_dict(),
            "ppt": self.ppt.to_dict(),
            "shell": self.shell.to_dict(),
        }


CONFIG_CLASSES: Dict[str, Any] = {
    "live2d": Live2DConfig,
    "obs": ObsConfig,
    "browser": BrowserConfig,
    "qqbot": QQBotConfig,
    "ppt": PptConfig,
    "shell": ShellConfig,
}


def get_service_classes(service_id: str):
    """返回配置类；未知 id 返回 None，由调用方给出明确错误。"""
    return CONFIG_CLASSES.get(str(service_id))