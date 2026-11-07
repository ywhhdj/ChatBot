from .ocr import (
    FasterWhisperRuntime,
    PaddleOCRRuntime,
    TesseractRuntime,
    EasyOCRRuntime,
    UmiOCRRuntime,
)

RUNTIME_REGISTRY = {
    "faster-whisper": FasterWhisperRuntime,
    "paddleocr": PaddleOCRRuntime,
    "tesseract": TesseractRuntime,
    "easyocr": EasyOCRRuntime,
    "umiocr": UmiOCRRuntime,
}

__all__ = ["RUNTIME_REGISTRY"]