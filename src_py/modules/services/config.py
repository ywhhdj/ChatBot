from typing import Dict, List, Optional

from ..runtime import RuntimePath
from ..config.models import _BaseConfig, Field

class Live2DConfig(_BaseConfig):
    model_path: str = Field(
        default=RuntimePath.get_models_path("live2d/肥牛/hiyori_pro_mic.model3.json"),
        description="Live2D模型路径"
    )
    media_pipe_face_model_path: str = Field(
        default=RuntimePath.get_models_path("mediapipe/face_landmarker.task"),
        description="MediaPipe人脸检测模型路径"
    )
    is_face_detected: bool = Field(default=True,description="是否检测人脸")


class BrowserConfig(_BaseConfig):
    enabled:bool = Field(default=False,description="是否启用浏览器服务")
    browser_type:str= Field(default="chrome",description="浏览器类型")
    headless:bool = Field(default=True,description="是否无头模式")
    binary_path: str = Field(default=r"C:\Program Files\Google\Chrome\Application\chrome.exe",description="浏览器exe路径")
    cdp_url: str = Field(default="ws://127.0.0.1:9222",description="浏览器CDP URL")
    profile_name: str = Field(default="Default",description="浏览器配置文件名称")
    user_data_dir: str = Field(default="C:\\Users\\Administrator\\AppData\\Local\\Google\\Chrome\\User Data",description="浏览器用户数据目录")
    viewport: Optional[Dict[str, int]] = Field(default=None,description="浏览器视口")
    user_agent: Optional[str] = Field(default=None,description="浏览器用户代理")
    proxy: Optional[str] = Field(default=None,description="浏览器代理")


class ObsConfig(_BaseConfig):
    enabled:bool = Field(default=True,description="是否启用Obs服务")
    ip: str = Field(default="192.168.183.1",description="Obs服务IP地址")
    password: str = Field(default="iS7aZQOpCzWEhfj6",description="Obs服务密码")
    port: int = Field(default=4455,description="Obs服务端口号")

class BilibiliConfig(_BaseConfig):
    """B站配置"""
    enabled: bool = Field(default=False,description="是否启用B站直播")
    url: str = Field(default="https://www.bilibili.com/video/BV12J4114768",description="B站直播URL")

class QQBotConfig(_BaseConfig):
    appid: str = Field(default="1905169695",description="QQ机器人AppID")
    secret: str = Field(default="L6seRE2qfVLC3vohbWRNKHFEDDEFHKNR",description="QQ机器人Secret")
    enabled: bool = Field(default=False,description="是否启用QQ机器人")
    sandbox: bool = Field(default=False,description="是否沙箱模式")
    intents: int = 1 << 25  # GROUP_AT_MESSAGE_CREATE 等，按需位运算
    shard: List[int] = Field(default_factory=lambda: [0, 1])

