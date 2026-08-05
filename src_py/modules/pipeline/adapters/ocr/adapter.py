from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass
import os
from types import CoroutineType
from typing import Any
from inspect import iscoroutinefunction

from ....utils.util import get_device

class _OCRBaseAdapter(ABC):
    def __init__(self) -> None:
        self.last_image = None
        self.ocr = None
        self._initialized = False
        self.model_path = ""

    @abstractmethod
    def init_ocr(self,model_path: str):
        raise NotImplementedError("init_ocr method must be implemented")

    @abstractmethod
    def recognize(self, image_bytes: bytes) -> CoroutineType:
        """识别图片中的文本"""
        raise NotImplementedError("recognize method must be implemented")

    
    async def ensure_initialized(self):
        if not self._initialized:
            if iscoroutinefunction(self.init_ocr):
                await self.init_ocr(self.model_path)
            else:
                self.init_ocr(self.model_path)
            self._initialized = True
    
    def get_params(self) -> dict[str, bytes]:
        if self.last_image is None:
            raise ValueError("OCRAdapter must be called with recognize method first.")
        return {"last_image": self.last_image}
    
    @abstractmethod
    def close(self):
        raise NotImplementedError("close method must be implemented")

@dataclass
class OCRResult:
    text: str
    conf: float
    #位置信息
    bbox: list[float]

class PaddleOCRAdapter(_OCRBaseAdapter):
    def __init__(self):
        super().__init__()
        self.lang = "ch"
    
    async def init_ocr(self,model_path: str):
        self.model_path = model_path
        #ocr的det, rec, cls模型
        try:
            from paddleocr import PaddleOCR
            self.ocr = PaddleOCR(
                use_angle_cls=True,
                engine="paddle",
                device=get_device(),
                lang=self.lang,
                det_model_dir=os.path.join(self.model_path, "det"),
                rec_model_dir=os.path.join(self.model_path, "rec"),
                cls_model_dir=os.path.join(self.model_path, "cls")
            )
        except ImportError:
            raise ImportError("PaddleOCR is not installed.")

    async def recognize(self, image: bytes) -> str:
        await self.ensure_initialized()
        self.last_image = image
        # 向量计算，交给线程池处理
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self.ocr.predict, image) # type: ignore
        return result['text'] # type: ignore
    
    def close(self):
        if self.ocr is None:
            return
        self.ocr.close()
        self.ocr = None

class TesseractOCRAdapter(_OCRBaseAdapter):
    def __init__(self,lang: str = "chi_sim+eng"):
        super().__init__()
        self.lang = lang
    
    def init_ocr(self,model_path: str):
        self.model_path = model_path
        try:
            from pytesseract import image_to_string # type: ignore
            self.ocr = image_to_string
        except ImportError:
            raise ImportError("Tesseract is not installed.")
    
    async def recognize(self, image: bytes) -> str:
        """异步执行Tesseract OCR识别"""
        await self.ensure_initialized()
        self.last_image = image
        # 使用run_in_executor避免阻塞
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, 
            lambda: self.ocr(image, lang=self.lang) # type: ignore
        )
        return result
    
    def close(self):
        if self.ocr is None:
            return
        self.ocr.close()
        self.ocr = None

class UmiOCRAdapter(_OCRBaseAdapter):
    def __init__(self):
        super().__init__()
        self.ocr = None
    
    async def init_ocr(self,model_path: str):
        self.model_path = model_path
        try:
            from umiocr import UmiOCR # type: ignore
            self.ocr = UmiOCR()
        except ImportError:
            raise ImportError("UmiOCR is not installed.")
    
    async def recognize(self, image: bytes) -> str:
        await self.ensure_initialized()
        self.last_image = image
        
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self.ocr, image) # type: ignore
        return result
    
    def close(self):
        if self.ocr is None:
            return
        self.ocr.close()
        self.ocr = None

class EasyOCRAdapter(_OCRBaseAdapter):
    def __init__(self, languages: list[str] = ['ch_sim', 'en']):
        super().__init__()
        self.languages = languages
    
    async def init_ocr(self,model_path: str):
        self.model_path = model_path
        try:
            from easyocr import Reader # type: ignore
            # EasyOCR首次运行会自动下载模型
            loop = asyncio.get_event_loop()
            self.ocr = await loop.run_in_executor(
                None,
                lambda: Reader(self.languages, gpu=True)
            )
        except ImportError:
            raise ImportError("EasyOCR is not installed.")
    
    async def recognize(self, image: bytes) -> str:
        """异步执行EasyOCR识别"""
        await self.ensure_initialized()
        self.last_image = image
        
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self.ocr.readtext, image) # type: ignore
        return result[0][1]
    
    def close(self):
        if self.ocr is None:
            return
        self.ocr.close()
        self.ocr = None