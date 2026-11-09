from .faster_whisper import FasterWhisperRuntime
from .paddleocr import PaddleOCRRuntime
from .tesseract import TesseractRuntime
from .easyocr import EasyOCRRuntime
from .umiocr import UmiOCRRuntime

__all__ = [
    "FasterWhisperRuntime",
    "PaddleOCRRuntime",
    "TesseractRuntime",
    "EasyOCRRuntime",
    "UmiOCRRuntime",
]