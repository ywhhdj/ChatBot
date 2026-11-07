"""原子写入与路径安全原语"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from typing import Any, Callable, Optional

# ─────────────────────────────────────────────────────────────
# 路径安全
# ─────────────────────────────────────────────────────────────


def safe_join(root: str, *parts: str) -> str:
    """拼接并规范化，返回绝对路径。**结果一定在 root 内**，否则抛异常。

    注意：这里**不**允许通过 `..` 逃出 root。存档 id 可能来自
    用户输入或外部导入的存档包，拼接前必须过这一关。
    """
    root_abs = os.path.abspath(str(root))
    candidate = os.path.abspath(os.path.join(root_abs, *[str(p) for p in parts]))
    if not is_within(root_abs, candidate):
        raise ValueError(f"路径逃逸被拒绝: {candidate!r} 不在 {root_abs!r} 内")
    return candidate


def is_within(root: str, candidate: str) -> bool:
    """candidate 是否在 root 内（含 root 自身）"""
    root_abs = os.path.abspath(str(root))
    cand_abs = os.path.abspath(str(candidate))
    if root_abs == cand_abs:
        return True
    try:
        common = os.path.commonpath([root_abs, cand_abs])
    except ValueError:
        # 不同驱动器（Windows）
        return False
    return common == root_abs


# ─────────────────────────────────────────────────────────────
# 校验和
# ─────────────────────────────────────────────────────────────


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    """分块读，避免大文件一次性进内存。"""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(obj: Any) -> bytes:
    """规范化 JSON：key 排序 + 固定分隔符。

    同一个 dict 两次序列化必须得到**完全相同的字节**，
    否则 hash 对不上，快照校验会随机失败。
    """
    return json.dumps(
        obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")


# ─────────────────────────────────────────────────────────────
# 原子写
# ─────────────────────────────────────────────────────────────


def _fsync_dir(dirname: str) -> None:
    """目录 fsync。Windows 上无法可移植实现，失败静默跳过。"""
    try:
        fd = os.open(dirname, os.O_RDONLY)  # type: ignore[attr-defined]
    except (OSError, AttributeError):
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def atomic_write(path: str, write_fn: Callable[[str], None]) -> None:
    path = os.path.abspath(str(path))
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)

    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".part", dir=parent)
    try:
        os.close(fd)
        write_fn(tmp)
        with open(tmp, "rb") as fh:
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        _fsync_dir(parent)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_bytes(path: str, data: bytes) -> None:
    def _w(tmp: str) -> None:
        with open(tmp, "wb") as fh:
            fh.write(data)

    atomic_write(path, _w)


def atomic_write_text(path: str, text: str, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, text.encode(encoding))


def atomic_write_json(path: str, obj: Any) -> None:
    """写 JSON。用规范化字节，保证同内容同 hash。"""
    atomic_write_bytes(path, canonical_json_bytes(obj))


def atomic_write_yaml(path: str, obj: Any) -> None:

    atomic_write(path, yaml.write_yaml)


# ─────────────────────────────────────────────────────────────
# 目录级原子发布
# ─────────────────────────────────────────────────────────────


def atomic_publish_dir(staging_dir: str, target_dir: str) -> None:
    staging_dir = os.path.abspath(str(staging_dir))
    target_dir = os.path.abspath(str(target_dir))

    if not os.path.isdir(staging_dir):
        raise FileNotFoundError(f"staging 目录不存在: {staging_dir}")
    if os.path.exists(target_dir):
        raise FileExistsError(f"目标 revision 已存在，拒绝覆盖: {target_dir}")

    parent = os.path.dirname(target_dir) or "."
    os.makedirs(parent, exist_ok=True)
    os.replace(staging_dir, target_dir)
    _fsync_dir(parent)


def ensure_clean_dir(path: str) -> str:
    """确保目录存在且为空"""
    import shutil

    os.makedirs(path, exist_ok=True)
    for name in os.listdir(path):
        item = os.path.join(path, name)
        try:
            if os.path.isdir(item) and not os.path.islink(item):
                shutil.rmtree(item, ignore_errors=True)
            else:
                os.unlink(item)
        except OSError:
            pass
    return path
