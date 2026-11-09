from pathlib import Path
from typing import Union


def read_audio(file_path:Union[str, Path]) -> bytes:
    with open(file_path, "rb") as f:
        return f.read()

def write_audio(file_path: Union[str, Path], data:bytes):
    with open(file_path, "wb") as f:
        f.write(data)

def write_audio_chunks(audio_name: Union[str, Path], audio_chunks: list[bytes]):
    with open(f"{audio_name}.wav", "wb") as f:
        for chunk in audio_chunks:
            f.write(chunk)