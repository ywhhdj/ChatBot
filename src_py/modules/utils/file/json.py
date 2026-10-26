from typing import Any, Dict, List
from json import load,dump,JSONDecodeError,loads

from .common import FileType,ensure_file_exists,_open,check_file_exists

def read_json(file_path:FileType,encoding:str="utf-8"):
    if not check_file_exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    try:
        with _open(file_path, "r",encoding=encoding) as f:
            return load(f)
    except JSONDecodeError as e:
        raise RuntimeError(f"JSON file decode failed: {e}")

def write_json(
    file_path:FileType,
    data:Dict[str,Any]|List[Dict[str,Any]],
    encoding:str="utf-8",
    default:Any=None
):
    ensure_file_exists(file_path)
    try:
        with _open(file_path, "w",encoding=encoding) as f:
            dump(data, f, ensure_ascii=False, indent=2, default=default)
    except Exception as e:
        raise RuntimeError(f"Write JSON file failed: {e}")
