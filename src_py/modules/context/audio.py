from pathlib import Path
from threading import Lock
from typing import Dict
import uuid
from ..runtime import RuntimePath

DEFAULT_AUDIO_DIR=RuntimePath.get_static_path("audios")

class AudioContext:
    _instance = None
    _intialized = False
    _lock = Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if not cls._instance:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, audio_dir: str|Path=DEFAULT_AUDIO_DIR) -> None:
        # if self._intialized:
        #     return
        self._instance = self
        self.audio_dir = audio_dir
        self.audio_chunks: Dict[str, list[bytes]] = {}
        self.current_audio_name: str = "audio_"
        self.current_audio_chunks: list[bytes] = []
        self.all_audio_paths: Dict[str, list[str]] = {}
        # self._intialized = True
    
    def get_all_audio_paths(self,category: str="default") -> list[str]:
        return self.all_audio_paths[category] #返回音频文件路径给前端播放
    
    def add_audio_chunk(self, chunk: bytes) -> None:
        self.current_audio_chunks.append(chunk)
    
    def get_current_audio(self) -> str:
        return f"{self.audio_dir}/{self.current_audio_name}.wav"
    
    def get_current_audio_bytes(self) -> bytes:
        return b"".join(self.current_audio_chunks)
    
    # 重置当前音频上下文，生成新的音频文件
    def reset_current_audio(self,category: str="default") -> None:
        # with self._lock:
            self.current_audio_name = f"audio_{uuid.uuid4().hex[:8]}_{len(self.audio_chunks)+1}"
            self.current_audio_chunks = []
            self.audio_chunks[self.current_audio_name] = self.current_audio_chunks
            self.save_audio_chunks(self.audio_chunks,category)
    from ..manager.task.decorator import sync_task_scheduler
    @sync_task_scheduler
    def save_audio_chunks(self, chunks: Dict[str, list[bytes]],category: str) -> None:
        if not chunks:
            return
        if len(self.audio_chunks) <= 5:
            return
        from ..utils.audio import write_audio_chunks
        for name, audio_chunks in self.audio_chunks.items():
            path = Path(self.audio_dir) / f"{name}.wav"
            self.all_audio_paths[category].append(str(path))
            write_audio_chunks(path, audio_chunks)
            del self.audio_chunks[name]

