from typing import Any, Dict

from .common import FileType,ensure_file_exists,_open,check_file_exists

def read_env(env_path: FileType):
    if not check_file_exists(env_path):
        return None
    env_dict = {}
    current_section="" 
    try:
        with _open(env_path, "r",encoding="utf-8") as f:
            for line in f:
                try:
                    line=line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if "#" in line:
                        line=line.split("#")[0].strip()
                    if line.startswith("[") and line.endswith("]"):
                        current_section=line[1:-1].split()[0].strip().upper()
                        env_dict[current_section]={}
                        continue
                    if "="  not in line:
                        continue
                    key, value = line.split("=",1)
                    if "#" in value:
                        value=value.split("#")[0].strip()
                    else:
                        value=value.strip()
                    if value.lower() in ("true", "false"):
                        value=bool(value.lower()=="true")
                    elif value.isdigit():
                        value=int(value)
                    elif (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
                        value=value[1:-1]
                    #如果是,则转换为列表
                    elif "," in value:
                        v=value.split(",")
                        value=[]
                        for item in v:
                            item=item.strip()
                            if item:
                                value.append(item)
                    env_dict[current_section][key.strip()] = value
                except Exception as e:
                    raise e
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {env_path}")
    except PermissionError:
        raise PermissionError(f"Permission denied: {env_path}")
    except Exception as e:
        raise e

def write_env(env_path: FileType, env_dict: Dict[str, Dict[str, Any]]) -> None:
    ensure_file_exists(env_path)
    with _open(env_path, "w",encoding="utf-8") as f:
        for section, items in env_dict.items():
            f.write(f"[{section}]\n")
            for key, value in items.items():
                if isinstance(value, str):
                    value=f"'{value}'"
                elif isinstance(value, bool):
                    if value:
                        value="true"
                    else:
                        value="false"
                elif isinstance(value, list):
                    value=f"[{','.join(map(str, value))}]"
                else:
                    value=str(value)
                if isinstance(value, str):
                    value=value.replace("\n", " ")
                f.write(f"{key}={value}\n")
            f.write("\n")
