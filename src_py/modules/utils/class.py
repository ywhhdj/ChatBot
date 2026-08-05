from typing import Any

def get_all_methods(object:Any) -> list[str]:
        return [method for method in dir(object) if callable(getattr(object, method)) and not method.startswith("_")]
