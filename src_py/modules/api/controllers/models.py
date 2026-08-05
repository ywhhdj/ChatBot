from typing import Any, Dict, Optional
from pydantic import BaseModel

class WebSocketRequest(BaseModel):
    type: str
    data: Optional[Dict[str, Any]]
    timestamp: Optional[int]