from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

@dataclass
class DownloadItem:
    name: str
    url: str
    target: Path             # 文件或解压目录
    archive: Optional[str] = None   # "tar" / "zip" / None


@dataclass
class DownloadPlan:
    capability: str
    provider: str
    strategy: str
    target_dir: Path
    items: List[DownloadItem]
    meta: Dict[str, Any] = field(default_factory=dict)