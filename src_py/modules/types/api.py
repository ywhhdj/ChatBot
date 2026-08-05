from typing import Any, Optional

from pydantic import BaseModel

class ConfigDescriptionItem(BaseModel):
    name: str
    description: Optional[str] = None
    value: Any
    options: Optional[list[str]] = None


class ServiceConfigDescription(BaseModel):
    name: str
    description: str
    config: list[ConfigDescriptionItem]
