"""二进制存档容器 `saves/<slot_id>.save`。

为什么改成二进制
────────────────
YAML 存档是**文本**：写入中途崩溃会留下半截文件（已用原子写缓解），
但更麻烦的是它**没有完整性校验** —— 文件被截断、被别的程序改了几个字节、
或者拷到一半，`yaml.safe_load` 可能照样解析出一个"看起来正常"的槽，
只是悄悄少了几个字段。用户不会收到任何提示，直到某天恢复时才发现。

二进制容器把"完整性"变成读档时必须过的第一道关：
magic / version / 尾部 sha256 / 每个 section 独立 sha256 / 偏移与长度边界，
任何一项不符都**明确拒绝**并返回稳定的 reason code，而不是尽力解析。

布局（小端）
──────────
```
offset  size   field
0       8      magic  b"CBSAVE\x00\x01"
8       4      header_len  (uint32)
12      N      header      (canonical JSON, UTF-8)
12+N    M      sections    (按 header 里的 offset 拼接的二进制块)
...     32     trailer     sha256(前面所有字节)
```

**header 与 section 都是长度前缀的**，不依赖换行或分隔符，
因此 section 内容可以是任意字节（未来放模型权重/音频/图片也不需要改格式）。

与 Memento 快照的关系
────────────────────
`.save` 是**槽的当前状态**；`snapshots/rev-*` 是历史 revision。
两者互不替代：当前状态频繁覆盖写，历史 revision 一旦发布不得修改。
存档完整性校验在这里，快照一致性校验在 `memento.py`。

秘密
────
写档前对配置段做脱敏（只留遮蔽值），并在 header 记 `redactions`。
恢复时密钥应由独立安全配置库重新校验是否已配置，而不是从存档还原。
"""

from __future__ import annotations

import hashlib
import json
import os
import struct
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ...utils.file.atomic import (
    atomic_write_bytes,
    canonical_json_bytes,
)

# ─────────────────────────────────────────────────────────────
# 常量
# ─────────────────────────────────────────────────────────────

MAGIC = b"CBSAVE\x00\x01"
HEADER_LEN_SIZE = 4
TRAILER_SIZE = 32
FORMAT = "chatbot-save"
SCHEMA_VERSION = 1
SUPPORTED_VERSIONS = frozenset({1})

#: 整档体积上限。防止一个损坏的长度字段导致读档时分配巨量内存。
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_SECTIONS = 64

#: 单段上限（与 memento 一致）
MAX_SECTION_SIZE = 64 * 1024 * 1024


class SaveReject(str, Enum):
    """读档拒绝原因。稳定低基数，不拼自由文本进日志。"""

    OK = "ok"
    TOO_SMALL = "too_small"
    BAD_MAGIC = "bad_magic"
    BAD_HEADER_LEN = "bad_header_len"
    BAD_HEADER_JSON = "bad_header_json"
    UNSUPPORTED_VERSION = "unsupported_version"
    BAD_FORMAT = "bad_format"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    BAD_SECTION_TABLE = "bad_section_table"
    SECTION_OUT_OF_BOUNDS = "section_out_of_bounds"
    SECTION_HASH_MISMATCH = "section_hash_mismatch"
    TOO_MANY_SECTIONS = "too_many_sections"
    TOO_LARGE = "too_large"
    IO_ERROR = "io_error"


@dataclass(frozen=True)
class SectionRecord:
    name: str
    kind: str = ""
    schema_version: int = 1
    offset: int = 0
    length: int = 0
    sha256: str = ""
    #: 是否只是路径引用（不能声称是完整数据）
    reference_only: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "schema_version": int(self.schema_version),
            "offset": int(self.offset),
            "length": int(self.length),
            "sha256": self.sha256,
            "reference_only": bool(self.reference_only),
        }

    @staticmethod
    def from_dict(raw: Any) -> Optional["SectionRecord"]:
        if not isinstance(raw, dict):
            return None
        try:
            return SectionRecord(
                name=str(raw.get("name", "") or ""),
                kind=str(raw.get("kind", "") or ""),
                schema_version=int(raw.get("schema_version", 1) or 1),
                offset=int(raw.get("offset", 0) or 0),
                length=int(raw.get("length", 0) or 0),
                sha256=str(raw.get("sha256", "") or ""),
                reference_only=bool(raw.get("reference_only", False)),
            )
        except (TypeError, ValueError):
            return None


@dataclass(frozen=True)
class SaveArchive:
    """读出来的存档。**frozen**：交给调用方后不可被中途改写。"""

    slot_id: str = ""
    name: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    schema_version: int = SCHEMA_VERSION
    sections: Tuple[SectionRecord, ...] = ()
    payloads: Mapping[str, Any] = None  # type: ignore[assignment]
    meta: Mapping[str, Any] = None  # type: ignore[assignment]
    redactions: Tuple[str, ...] = ()

    def section(self, name: str) -> Any:
        return (self.payloads or {}).get(name)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "slot_id": self.slot_id,
            "name": self.name,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "sections": [s.to_dict() for s in self.sections],
            "redactions": list(self.redactions),
        }


# ─────────────────────────────────────────────────────────────
# 写
# ─────────────────────────────────────────────────────────────


def build_bytes(
    *,
    slot_id: str,
    name: str,
    sections: Mapping[str, Any],
    kinds: Optional[Mapping[str, str]] = None,
    reference_only: Optional[Mapping[str, bool]] = None,
    created_at: float = 0.0,
    meta: Optional[Mapping[str, Any]] = None,
    redactions: Tuple[str, ...] = ("provider_secrets",),
) -> bytes:
    """构造完整存档字节（纯函数，不碰磁盘）。

    `sections` 的值是任意可 JSON 序列化对象。每段独立算 hash，
    这样将来某一段被改坏时能明确报出**是哪一段**，而不是只有一个全局错。
    """
    kinds = dict(kinds or {})
    reference_only = dict(reference_only or {})
    blobs: List[Tuple[str, bytes]] = []
    for section_name, value in (sections or {}).items():
        raw = canonical_json_bytes(value)
        if len(raw) > MAX_SECTION_SIZE:
            raise ValueError(f"section {section_name} 超过 {MAX_SECTION_SIZE} 字节")
        blobs.append((str(section_name), raw))

    if len(blobs) > MAX_SECTIONS:
        raise ValueError(f"section 数量超过 {MAX_SECTIONS}")

    now = time.time()
    records: List[SectionRecord] = []
    body = bytearray()
    for section_name, raw in blobs:
        records.append(SectionRecord(
            name=section_name,
            kind=str(kinds.get(section_name, "") or ""),
            schema_version=1,
            offset=len(body),
            length=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
            reference_only=bool(reference_only.get(section_name, False)),
        ))
        body.extend(raw)

    header = {
        "format": FORMAT,
        "schema_version": SCHEMA_VERSION,
        "slot_id": str(slot_id or ""),
        "name": str(name or ""),
        "created_at": float(created_at or now),
        "updated_at": float(now),
        "sections": [r.to_dict() for r in records],
        "meta": dict(meta or {}),
        "redactions": list(redactions),
    }
    header_bytes = canonical_json_bytes(header)
    if len(header_bytes) > 16 * 1024 * 1024:
        raise ValueError("存档 header 过大")

    out = bytearray()
    out.extend(MAGIC)
    out.extend(struct.pack("<I", len(header_bytes)))
    out.extend(header_bytes)
    out.extend(body)
    out.extend(hashlib.sha256(bytes(out)).digest())

    if len(out) > MAX_ARCHIVE_BYTES:
        raise ValueError(f"存档超过 {MAX_ARCHIVE_BYTES} 字节上限")
    return bytes(out)


def write_archive(path: str, **kwargs: Any) -> bool:
    """原子写档。

    复用 `atomic_write_bytes`：同目录临时文件 → fsync → os.replace。
    写失败时**旧的 .save 原封不动**，不会留下半截文件。
    """
    try:
        data = build_bytes(**kwargs)
    except (ValueError, TypeError) as exc:
        from ...logger import logger

        logger.error(f"[SaveArchive] 构造存档失败: {type(exc).__name__}")
        return False
    try:
        atomic_write_bytes(path, data)
        return True
    except OSError:
        from ...logger import logger

        logger.error("[SaveArchive] 原子写档失败")
        return False


# ─────────────────────────────────────────────────────────────
# 读
# ─────────────────────────────────────────────────────────────


def read_bytes(data: bytes) -> Tuple[Optional[SaveArchive], SaveReject, str]:
    """校验并解析存档字节。**纯函数**。

    校验顺序刻意从便宜到昂贵：magic → 长度 → 全局 hash → header →
    每段 hash。任何一步失败立即返回 reason code，绝不做"尽力解析"。
    """
    size = len(data)
    minimum = len(MAGIC) + HEADER_LEN_SIZE + TRAILER_SIZE
    if size < minimum:
        return None, SaveReject.TOO_SMALL, "文件过短，不是有效存档"

    if data[:len(MAGIC)] != MAGIC:
        return None, SaveReject.BAD_MAGIC, "magic 不匹配"

    if size > MAX_ARCHIVE_BYTES:
        return None, SaveReject.TOO_LARGE, "存档超过体积上限"

    body_end = size - TRAILER_SIZE
    expected = data[body_end:]
    actual = hashlib.sha256(data[:body_end]).digest()
    if actual != expected:
        return None, SaveReject.CHECKSUM_MISMATCH, (
            "存档整体校验失败：文件被截断、被修改或拷贝不完整"
        )

    try:
        header_len = struct.unpack("<I", data[len(MAGIC):len(MAGIC) + HEADER_LEN_SIZE])[0]
    except struct.error:
        return None, SaveReject.BAD_HEADER_LEN, "header 长度无法解析"

    header_start = len(MAGIC) + HEADER_LEN_SIZE
    header_end = header_start + int(header_len)
    if header_len <= 0 or header_end > body_end:
        return None, SaveReject.BAD_HEADER_LEN, "header 长度越界"

    try:
        header = json.loads(data[header_start:header_end].decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None, SaveReject.BAD_HEADER_JSON, "header 不是合法 JSON"

    if not isinstance(header, dict):
        return None, SaveReject.BAD_HEADER_JSON, "header 不是对象"
    if str(header.get("format", "")) != FORMAT:
        return None, SaveReject.BAD_FORMAT, "format 不匹配"

    try:
        version = int(header.get("schema_version", -1))
    except (TypeError, ValueError):
        return None, SaveReject.UNSUPPORTED_VERSION, "schema_version 无法解析"
    if version not in SUPPORTED_VERSIONS:
        return None, SaveReject.UNSUPPORTED_VERSION, (
            f"未知存档版本 {version}（支持 {sorted(SUPPORTED_VERSIONS)}）"
        )

    raw_sections = header.get("sections")
    if not isinstance(raw_sections, list):
        return None, SaveReject.BAD_SECTION_TABLE, "section 表不是数组"
    if len(raw_sections) > MAX_SECTIONS:
        return None, SaveReject.TOO_MANY_SECTIONS, "section 数量超过上限"

    records: List[SectionRecord] = []
    for raw in raw_sections:
        rec = SectionRecord.from_dict(raw)
        if rec is None or not rec.name:
            return None, SaveReject.BAD_SECTION_TABLE, "section 记录非法"
        records.append(rec)

    payloads: Dict[str, Any] = {}
    data_start = header_end
    for rec in records:
        start = data_start + rec.offset
        end = start + rec.length
        if rec.offset < 0 or rec.length < 0 or end > body_end:
            return None, SaveReject.SECTION_OUT_OF_BOUNDS, (
                f"section {rec.name} 偏移/长度越界"
            )
        blob = data[start:end]
        if hashlib.sha256(blob).hexdigest() != rec.sha256:
            return None, SaveReject.SECTION_HASH_MISMATCH, (
                f"section {rec.name} 内容校验失败"
            )
        try:
            payloads[rec.name] = json.loads(blob.decode("utf-8"))
        except Exception:  # noqa: BLE001
            return None, SaveReject.SECTION_HASH_MISMATCH, (
                f"section {rec.name} 不是合法 JSON"
            )

    archive = SaveArchive(
        slot_id=str(header.get("slot_id", "") or ""),
        name=str(header.get("name", "") or ""),
        created_at=float(header.get("created_at", 0.0) or 0.0),
        updated_at=float(header.get("updated_at", 0.0) or 0.0),
        schema_version=version,
        sections=tuple(records),
        payloads=payloads,
        meta=dict(header.get("meta") or {}),
        redactions=tuple(str(r) for r in (header.get("redactions") or ())),
    )
    return archive, SaveReject.OK, ""


def read_archive(path: str) -> Tuple[Optional[SaveArchive], SaveReject, str]:
    """读档。文件不存在/读失败都返回稳定 code，不抛异常给控制器。"""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except FileNotFoundError:
        return None, SaveReject.IO_ERROR, "存档文件不存在"
    except OSError:
        return None, SaveReject.IO_ERROR, "存档文件无法读取"
    return read_bytes(data)


def verify_file(path: str) -> Tuple[bool, SaveReject, str]:
    """只校验完整性，不解析 section 内容（体检接口用）。"""
    archive, code, msg = read_archive(path)
    return archive is not None, code, msg
