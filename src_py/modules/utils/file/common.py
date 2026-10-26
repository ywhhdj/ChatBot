import io
import os
from pathlib import Path

FileType = str|Path

def remove_file(file_path:FileType) -> None:
    if check_exists(file_path):
        os.remove(file_path)

def ensure_file_exists(file_path:FileType):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

def _open(f:FileType,mode='r', buffering=-1, encoding=None,errors=None, newline=None):
    if "b" not in mode:
        encoding = io.text_encoding(encoding)
    return io.open(f,mode, buffering, encoding, errors, newline)

def check_exists(file_path:FileType) -> bool:
    return os.path.exists(file_path)

def check_file_exists(file_path:FileType):
    if isinstance(file_path,str):
        file_path=file_path.rstrip("/")
    return check_exists(file_path) and os.path.isfile(file_path)

def read_text(file_path:FileType,encoding:str="utf-8") -> str:
    if not check_file_exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    try:
        with _open(file_path, "r",encoding=encoding) as f:
            return f.read().strip()
        return ""
    except Exception as e:
        raise RuntimeError(f"Read text file failed: {e}")

def read_markdown(file_path:FileType,encoding:str="utf-8") -> str:
    return read_text(file_path,encoding)
