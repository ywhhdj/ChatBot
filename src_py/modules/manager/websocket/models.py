from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

@dataclass
class ConnectionInfo:
    client_id: str
    connected_at: datetime = field(default_factory=datetime.now)
    last_heartbeat: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)

    def update_heartbeat(self):
        self.last_heartbeat = datetime.now()

    def is_alive(self, timeout_seconds: int = 60) -> bool:
        return (datetime.now() - self.last_heartbeat).total_seconds() < timeout_seconds

@dataclass
class WebSocketResponse:
    type: str
    data: Optional[Any] = None
    from_: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "data": self.data,
            "from": self.from_
        }