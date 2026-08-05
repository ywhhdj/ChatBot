from enum import Enum

class AdapterType(str, Enum):
    TTS = "tts"
    LLM = "llm"
    OCR = "ocr"
    ASR = "asr"

class TTSProviderType(str, Enum):
    GPTSoVITS = "GPTSoVITS"
    Vits = "Vits"

class LLMProviderType(str, Enum):
    DeepSeek = "DeepSeek"
    ChatGPT = "ChatGPT"
    Ollama = "Ollama"

class ASRProviderType(str, Enum):
    BAIDU = "baidu"
    OPENAI_WISPER = "whisper"
    TENCENT_CLOUD = "tencent_cloud"

class OCRProviderType(str, Enum):
    Paddle="paddleocr"
    Easy="easyocr"
    UMI="umi"