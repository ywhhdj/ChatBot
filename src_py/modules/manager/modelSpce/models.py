#模型的状态等
from typing import Optional
from pydantic import BaseModel


class ModelStatus(BaseModel):
    id: str
    download: bool = False
    description: Optional[str] = None
    