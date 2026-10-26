from typing import Any
import pickle

from .common import FileType,ensure_file_exists,_open,check_file_exists

def read_pickle(file_path:FileType) -> Any:
    if not check_file_exists(file_path):
        raise FileNotFoundError(f"File {file_path} not found")
    try:
        with _open(file_path, "rb") as f:
            return pickle.load(f)
    except Exception as e:
        raise RuntimeError(f"Read pickle file failed: {e}")

def write_pickle(file_path:FileType,data:Any) -> None:
    ensure_file_exists(file_path)
    try:
        with _open(file_path, "wb") as f:
            pickle.dump(data, f)
    except Exception as e:
        raise RuntimeError(f"Write pickle file failed: {e}")