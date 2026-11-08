"""app.conf 读写"""
from typing import Any, Dict

from ..utils.file.common import FileType, ensure_file_exists, _open, check_file_exists

_LIST_KEYS = frozenset({"allow_origins", "allow_methods", "allow_headers"})


def _coerce(value: str) -> Any:
    text = value.strip()
    lowered = text.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    if text.isdigit():
        return int(text)
    if (text.startswith("'") and text.endswith("'")) or (
        text.startswith('"') and text.endswith('"')
    ):
        return text[1:-1]
    if "," in text:
        return [item.strip() for item in text.split(",") if item.strip()]
    return text


def read_app_config(env_path: FileType):
    if not check_file_exists(env_path):
        return None
    env_dict: Dict[str, Dict[str, Any]] = {}
    current_section = ""
    try:
        with _open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                hash_at = line.find("#")
                if hash_at >= 0 and (hash_at == 0 or line[hash_at - 1].isspace()):
                    line = line[:hash_at].strip()
                if not line:
                    continue
                if line.startswith("[") and line.endswith("]"):
                    current_section = line[1:-1].split()[0].strip().upper()
                    env_dict.setdefault(current_section, {})
                    continue
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip().lower()
                parsed = _coerce(value)
                if key in _LIST_KEYS and isinstance(parsed, str):
                    parsed = [parsed]
                env_dict.setdefault(current_section, {})[key] = parsed
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {env_path}")
    except PermissionError:
        raise PermissionError(f"Permission denied: {env_path}")
    return env_dict


def write_app_config(env_path: FileType, env_dict: Dict[str, Dict[str, Any]]) -> None:
    ensure_file_exists(env_path)
    with _open(env_path, "w", encoding="utf-8") as f:
        for section, items in env_dict.items():
            f.write(f"[{section}]\n")
            for key, value in items.items():
                if isinstance(value, str):
                    value = f"'{value}'"
                elif isinstance(value, bool):
                    value = "true" if value else "false"
                elif isinstance(value, list):
                    value = f"[{','.join(map(str, value))}]"
                else:
                    value = str(value)
                if isinstance(value, str):
                    value = value.replace("\n", " ")
                f.write(f"{key}={value}\n")
            f.write("\n")
