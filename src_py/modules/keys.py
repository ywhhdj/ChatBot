class ProviderType:
    TTS = "tts"
    LLM = "llm"
    OCR = "ocr"
    ASR = "asr"
    IMAGE = "image"


class ServiceKeys:
    BROWSER = "browser"
    LIVE2D = "live2d"
    OBS = "obs"
    QQBOT = "qqbot"
    PPT = "ppt"
    SHELL = "shell"

ALL_SERVICE_IDS = (
    ServiceKeys.BROWSER,
    ServiceKeys.LIVE2D,
    ServiceKeys.OBS,
    ServiceKeys.QQBOT,
    ServiceKeys.PPT,
    ServiceKeys.SHELL,
)

__all__ = ["ProviderType", "ServiceKeys", "ServiceKeys", "ALL_SERVICE_IDS"]
