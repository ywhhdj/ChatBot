from typing import Dict,Any
import yaml
from .common import check_file_exists,ensure_file_exists,_open,FileType

def write_yaml(file_path:FileType,data:Dict[str,Any],encoding:str="utf-8"):
    ensure_file_exists(file_path)
    try:
        with _open(file_path, "w",encoding=encoding) as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True,indent=4)
    except Exception as e:
        raise RuntimeError(f"Write YAML file failed: {e}")

def parse_yaml(data):
    try:
        return yaml.safe_load(data)
    except Exception as e:
        raise RuntimeError(f"Parse YAML data failed: {e}")

def read_yaml(file_path:FileType,encoding:str="utf-8") -> Dict[str,Any]:
    if not check_file_exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    try:
        with _open(file_path, "r",encoding=encoding) as f:
            return parse_yaml(f.read())
    except Exception as e:
        raise RuntimeError(f"Read YAML file failed: {e}")


