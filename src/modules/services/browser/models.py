from dataclasses import dataclass, field
from typing import Dict, List, Optional

@dataclass
class DomElement:
    uid: str
    tag: str
    text: str = ""
    href: str = ""
    aria_label: str = ""
    placeholder: str = ""
    input_type: str = ""
    role: str = ""
    selector: str = ""
    xpath: str = ""
    rect: Dict[str, float] = field(default_factory=dict)
    in_viewport: bool = True
    z_index: int = 0
    is_visible: bool = True
    is_interactive: bool = False
    similarity_hash: str = ""
    depth: int = 0


@dataclass
class DomChunk:
    chunk_index: int
    total_chunks: int
    elements: List[DomElement]
    total_tokens_estimate: int


@dataclass
class DistilledDOM:
    url: str
    title: str
    total_original_elements: int
    total_after_filter: int
    compression_ratio: float
    chunks: List[DomChunk]
    stats: Dict[str, int] = field(default_factory=dict)
    version: Optional[int] = None