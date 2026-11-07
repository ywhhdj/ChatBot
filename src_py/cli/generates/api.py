"""scan_controllers.py：扫 controller 的 router 生成 endpoints.json。"""
import ast, json, sys
from pathlib import Path

def scan(path: Path, module_prefix: str):
    tree = ast.parse(path.read_text("utf-8"))
    out = []
    prefix = ""
    tags = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "router" for t in node.targets
        ):
            if isinstance(node.value, ast.Call):
                for kw in node.value.keywords:
                    if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                        prefix = kw.value.value
                    if kw.arg == "tags" and isinstance(kw.value, ast.List):
                        tags = [e.value for e in kw.value.elts if isinstance(e, ast.Constant)]
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            if not (isinstance(dec.func, ast.Attribute) and isinstance(dec.func.value, ast.Name)
                    and dec.func.value.id == "router"):
                continue
            method = dec.func.attr.upper()
            if node.name.startswith("_"):
                continue
            path = dec.args[0].value if dec.args and isinstance(dec.args[0], ast.Constant) else "" #type:ignore
            full_path = (prefix + path).replace("//", "/") or "/" #type:ignore
            out.append({
                "op": f"{module_prefix}.{node.name}",
                "handler": f"modules.api.controllers.{module_prefix}:{node.name}",
                "http": {"method": method, "path": full_path},
                "tags": tags or [module_prefix],
                "desktop": True,
                "meta": {"label": node.name},
            })
    return out

#获取根目录
root = Path(sys.argv[0]).parent.parent.parent.parent

if __name__ == "__main__":
    base = Path(f"{root}/src_py/modules/api/controllers")
    all_eps = []
    for f in base.glob("*.py"):
        if f.stem in ("__init__", "websocket"):
            continue
        all_eps.extend(scan(f, f.stem))
    Path(f"{root}/resources/config/api/endpoints.json").write_text(
        json.dumps({
            "version": 1,
            "endpoints": all_eps
        }, ensure_ascii=False, indent=2),
        "utf-8",
    )
    print(f"生成 {len(all_eps)} 个端点")