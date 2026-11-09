"""存档快照（Memento）的 manifest、revision 发布与恢复预演。

对应 B1-01 / B1-02 / B1-03。

职责边界
────────
本模块只管快照的文件层：manifest schema、revision 目录布局、
原子发布、恢复前的只读校验。它不读领域对象的私有状态，
也不代替各管理器做序列化——那是各 originator 的 `export_snapshot()`
"""

from __future__ import annotations

import os
import re
import time
import uuid
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from ...utils.file.atomic import (
    atomic_publish_dir,
    atomic_write_json,
    canonical_json_bytes,
    ensure_clean_dir,
    file_size,
    is_within,
    read_json,
    safe_join,
    sha256_bytes,
    sha256_file,
)

# ─────────────────────────────────────────────────────────────
# 常量
# ─────────────────────────────────────────────────────────────

FORMAT = "chatbot-snapshot"

#: 当前 manifest schema 版本。改动 manifest 字段语义时必须 +1。
SCHEMA_VERSION = 1

#: 能读懂的版本。**看不懂的一律拒绝**，不猜。
SUPPORTED_SCHEMA_VERSIONS = frozenset({1})

#: section 的 schema 版本（领域 DTO 自己的版本，与 manifest 分开）
SECTION_SCHEMA_VERSION = 1

_REVISION_RE = re.compile(r"^rev-\d{6,}$")

#: 快照体积与规模上限（§8 防耗尽）
MAX_SECTION_BYTES = 64 * 1024 * 1024
MAX_SECTIONS = 64


class ConsistencyLevel(str, Enum):
    """一致性等级（GameSaveArchitecture §3）。

    存档必须**声明**自己捕获到了什么程度。
    不声明就等于默认"完整"，而当前实现其实只存了路径指针。
    """

    #: S0：只有槽元数据与路径指针
    METADATA = "metadata"
    #: S1：已声明 section 的 revision 与路径引用，不保证历史文件独立复制
    CHECKPOINT = "checkpoint"
    #: S2：所有已注册 originator 的完整数据或不可变 artifact
    FULL = "full"
    #: S3：S2 + 迁移元数据 + 资产清单 + 恢复校验
    RECOVERY = "recovery"


class RevisionStatus(str, Enum):
    """revision 生命周期（§8）。

    `staging → prepared → committed → superseded → eligible_for_gc → deleted`

    **committed 之后不得原地编辑**。需要改就发新 revision。
    """

    STAGING = "staging"
    PREPARED = "prepared"
    COMMITTED = "committed"
    SUPERSEDED = "superseded"
    ELIGIBLE_FOR_GC = "eligible_for_gc"
    DELETED = "deleted"


class RejectCode(str, Enum):
    """拒绝/通过原因。稳定低基数，不含自由文本（SecurityAndAuditDesign §5）。"""

    OK = "ok"
    BAD_FORMAT = "bad_format"
    UNSUPPORTED_SCHEMA = "unsupported_schema"
    MISSING_FIELD = "missing_field"
    BAD_REVISION = "bad_revision"
    BAD_LEVEL = "bad_level"
    BAD_STATUS = "bad_status"
    SECTION_MISSING = "section_missing"
    SECTION_HASH_MISMATCH = "section_hash_mismatch"
    SECTION_TOO_LARGE = "section_too_large"
    TOO_MANY_SECTIONS = "too_many_sections"
    NOT_COMMITTED = "not_committed"
    PATH_ESCAPE = "path_escape"
    REVISION_EXISTS = "revision_exists"
    NO_CURRENT = "no_current"
    IO_ERROR = "io_error"


class MigrationAction(str, Enum):
    """恢复时需要执行的迁移动作。"""

    NONE = "none"
    #: section schema 低于当前，需要升级
    UPGRADE_SECTION = "upgrade_section"
    #: section schema 高于当前，**不能降级**，需要拒绝或提示升级应用
    DOWNGRADE_BLOCKED = "downgrade_blocked"
    #: section 在快照里缺失，恢复时该域保持现状
    SECTION_ABSENT = "section_absent"


# ─────────────────────────────────────────────────────────────
# 领域归属（恢复预演要用）
# ─────────────────────────────────────────────────────────────

#: section 名 → 归属的领域模块。恢复时按此顺序应用，
#: 且用于生成"这次恢复会覆盖哪些域"的可解释清单。
SECTION_OWNERS: Dict[str, str] = {
    "server_config": "config",
    "character": "character_manager",
    "session": "session_manager",
    "memory-manifest": "memory_system",
    "ui": "ui_state",
}

#: 恢复应用顺序。config 最先（后续模块可能读它），memory 最后（最重）。
RESTORE_ORDER: Tuple[str, ...] = (
    "server_config",
    "character",
    "session",
    "memory-manifest",
    "ui",
)


# ─────────────────────────────────────────────────────────────
# Manifest
# ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SectionEntry:
    """manifest 里一条 section 描述。"""

    name: str
    schema_version: int = SECTION_SCHEMA_VERSION
    sha256: str = ""
    bytes: int = 0
    kind: str = ""
    #: 该 section 是否只是引用（路径指针/外部不可快照）。
    #: True 时不能声称是完整快照。
    reference_only: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "kind": self.kind,
            "reference_only": self.reference_only,
        }

    @staticmethod
    def from_dict(name: str, raw: Any) -> "SectionEntry":
        raw = raw if isinstance(raw, dict) else {}
        return SectionEntry(
            name=str(name),
            schema_version=int(raw.get("schema_version", SECTION_SCHEMA_VERSION) or 0),
            sha256=str(raw.get("sha256", "") or ""),
            bytes=int(raw.get("bytes", 0) or 0),
            kind=str(raw.get("kind", "") or ""),
            reference_only=bool(raw.get("reference_only", False)),
        )


@dataclass(frozen=True)
class SnapshotManifest:
    """不可变快照清单。发布后**不得原地编辑**。"""

    slot_id: str = ""
    revision: str = ""
    schema_version: int = SCHEMA_VERSION
    parent_revision: str = ""
    created_at: str = ""
    app_version: str = ""
    consistency_level: str = ConsistencyLevel.CHECKPOINT.value
    operation_id: str = ""
    status: str = RevisionStatus.PREPARED.value
    sections: Tuple[SectionEntry, ...] = ()
    artifacts: Tuple[str, ...] = ()
    redactions: Tuple[str, ...] = ()
    # ── S2-02：时间线与分支（MementoMemoryIntegration §5）──
    # 三者都是**向后兼容的可选字段**：旧 manifest 没有它们，
    # validate_manifest 会补上缺省值（main / "" / manual）。
    #: 分支 id。缺省 main 表示主线
    branch_id: str = "main"
    #: 用户命名（可选）
    label: str = ""
    #: manual | quick | auto | pre-restore | pre-migration
    trigger: str = "manual"

    # ---------- 查询 ----------

    @property
    def section_map(self) -> Dict[str, SectionEntry]:
        return {s.name: s for s in self.sections}

    @property
    def committed(self) -> bool:
        return self.status == RevisionStatus.COMMITTED.value

    @property
    def has_reference_only(self) -> bool:
        """含引用型 section —— 不能声称是完整快照。"""
        return any(s.reference_only for s in self.sections)

    def effective_level(self) -> ConsistencyLevel:
        """实际一致性等级。

        声明 FULL 但含引用型 section，实际只能是 CHECKPOINT。
        这是诚实性检查：声明和实际必须一致，否则 FULL 就是虚假承诺。
        """
        try:
            level = ConsistencyLevel(self.consistency_level)
        except ValueError:
            return ConsistencyLevel.METADATA
        if level in (ConsistencyLevel.FULL, ConsistencyLevel.RECOVERY):
            if self.has_reference_only:
                return ConsistencyLevel.CHECKPOINT
        return level

    def level_is_overstated(self) -> bool:
        return self.effective_level().value != self.consistency_level

    # ---------- 序列化 ----------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "format": FORMAT,
            "schema_version": self.schema_version,
            "slot_id": self.slot_id,
            "revision": self.revision,
            "parent_revision": self.parent_revision,
            "created_at": self.created_at,
            "app_version": self.app_version,
            "consistency_level": self.consistency_level,
            "operation_id": self.operation_id,
            "status": self.status,
            "sections": {s.name: s.to_dict() for s in self.sections},
            "artifacts": list(self.artifacts),
            "redactions": list(self.redactions),
            "branch_id": self.branch_id,
            "label": self.label,
            "trigger": self.trigger,
        }

    def with_status(self, status: RevisionStatus) -> "SnapshotManifest":
        return replace(self, status=status.value)

    def with_sections(self, sections: Tuple[SectionEntry, ...]) -> "SnapshotManifest":
        return replace(self, sections=sections)

    def with_branch(
        self, *, branch_id: str = "", label: str = "", trigger: str = ""
    ) -> "SnapshotManifest":
        """发布前打分支标记。**返回新对象**，不改已发布 revision。"""
        return replace(
            self,
            branch_id=str(branch_id or self.branch_id or "main"),
            label=str(label or self.label),
            trigger=str(trigger or self.trigger or "manual"),
        )


def new_manifest(
    slot_id: str,
    revision: str,
    *,
    parent_revision: str = "",
    app_version: str = "",
    consistency_level: ConsistencyLevel = ConsistencyLevel.CHECKPOINT,
    operation_id: str = "",
    redactions: Tuple[str, ...] = (),
    branch_id: str = "main",
    label: str = "",
    trigger: str = "manual",
) -> SnapshotManifest:
    return SnapshotManifest(
        slot_id=str(slot_id),
        revision=str(revision),
        parent_revision=str(parent_revision or ""),
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        app_version=str(app_version or ""),
        consistency_level=consistency_level.value,
        operation_id=operation_id or uuid.uuid4().hex[:16],
        status=RevisionStatus.PREPARED.value,
        redactions=tuple(redactions),
        branch_id=str(branch_id or "main"),
        label=str(label or ""),
        trigger=str(trigger or "manual"),
    )


def validate_manifest(raw: Any) -> Tuple[Optional[SnapshotManifest], RejectCode, str]:
    """校验 manifest 对象。**纯函数**，不碰磁盘。

    未知 schema_version 一律拒绝（B1-01 验收：未知 schema 安全拒绝）。
    拒绝时返回 None + reason code，绝不做"尽力解析"。
    """
    if not isinstance(raw, dict):
        return None, RejectCode.BAD_FORMAT, "manifest 不是对象"

    if str(raw.get("format", "")) != FORMAT:
        return None, RejectCode.BAD_FORMAT, f"format 不是 {FORMAT}"

    try:
        version = int(raw.get("schema_version", -1))
    except (TypeError, ValueError):
        return None, RejectCode.UNSUPPORTED_SCHEMA, "schema_version 不可解析"

    if version not in SUPPORTED_SCHEMA_VERSIONS:
        return None, RejectCode.UNSUPPORTED_SCHEMA, (
            f"schema_version {version} 不受支持"
            f"（支持: {sorted(SUPPORTED_SCHEMA_VERSIONS)}）"
        )

    slot_id = str(raw.get("slot_id", "") or "")
    revision = str(raw.get("revision", "") or "")
    if not slot_id:
        return None, RejectCode.MISSING_FIELD, "缺少 slot_id"
    if not _REVISION_RE.match(revision):
        return None, RejectCode.BAD_REVISION, f"revision 格式非法: {revision!r}"

    level = str(raw.get("consistency_level", "") or "")
    try:
        ConsistencyLevel(level)
    except ValueError:
        return None, RejectCode.BAD_LEVEL, f"未知 consistency_level: {level!r}"

    status = str(raw.get("status", "") or "")
    try:
        RevisionStatus(status)
    except ValueError:
        return None, RejectCode.BAD_STATUS, f"未知 status: {status!r}"

    raw_sections = raw.get("sections") or {}
    if not isinstance(raw_sections, dict):
        return None, RejectCode.MISSING_FIELD, "sections 不是对象"
    if len(raw_sections) > MAX_SECTIONS:
        return None, RejectCode.TOO_MANY_SECTIONS, f"section 数量超过 {MAX_SECTIONS}"

    entries: List[SectionEntry] = []
    for name, desc in raw_sections.items():
        entry = SectionEntry.from_dict(str(name), desc)
        if entry.bytes > MAX_SECTION_BYTES:
            return None, RejectCode.SECTION_TOO_LARGE, f"section {name} 超过体积上限"
        entries.append(entry)

    manifest = SnapshotManifest(
        slot_id=slot_id,
        revision=revision,
        schema_version=version,
        parent_revision=str(raw.get("parent_revision", "") or ""),
        created_at=str(raw.get("created_at", "") or ""),
        app_version=str(raw.get("app_version", "") or ""),
        consistency_level=level,
        operation_id=str(raw.get("operation_id", "") or ""),
        status=status,
        sections=tuple(entries),
        artifacts=tuple(str(a) for a in (raw.get("artifacts") or ())),
        redactions=tuple(str(r) for r in (raw.get("redactions") or ())),
        branch_id=str(raw.get("branch_id", "") or "main")[:64],
        label=str(raw.get("label", "") or "")[:128],
        trigger=str(raw.get("trigger", "") or "manual")[:32],
    )
    return manifest, RejectCode.OK, ""


# ─────────────────────────────────────────────────────────────
# 目录布局
# ─────────────────────────────────────────────────────────────


def slot_dir(root: str, slot_id: str) -> str:
    return safe_join(root, "slots", str(slot_id))


def snapshots_dir(root: str, slot_id: str) -> str:
    return safe_join(root, "slots", str(slot_id), "snapshots")


def revision_dir(root: str, slot_id: str, revision: str) -> str:
    return safe_join(root, "slots", str(slot_id), "snapshots", str(revision))


def staging_dir(root: str, slot_id: str, operation_id: str) -> str:
    return safe_join(root, "slots", str(slot_id), "staging", str(operation_id))


def prepare_staging(root: str, slot_id: str, operation_id: str) -> str:
    """建（并清空）一个 staging 目录，返回其路径。

    staging 不是有效 revision：它只在发布成功后才变成 revision。
    启动时可直接清理 `staging/` 下所有残留（§5：崩溃后 staging 不得
    变成有效快照）。
    """
    return ensure_clean_dir(staging_dir(root, slot_id, operation_id))


def sections_dir(rev_dir: str) -> str:
    return os.path.join(rev_dir, "sections")


def manifest_path(rev_dir: str) -> str:
    return os.path.join(rev_dir, "manifest.json")


def current_pointer_path(root: str, slot_id: str) -> str:
    return safe_join(root, "slots", str(slot_id), "current.json")


# ─────────────────────────────────────────────────────────────
# 暂存与校验
# ─────────────────────────────────────────────────────────────


def write_section(
    target_dir: str,
    name: str,
    payload: Any,
    *,
    kind: str = "",
    reference_only: bool = False,
    schema_version: int = SECTION_SCHEMA_VERSION,
) -> SectionEntry:
    """把一个 section 写到 `target_dir/sections/<name>.json`。

    返回描述（含 sha256 与字节数）。用规范化 JSON，
    保证同内容同 hash —— 否则重读校验会随机失败。
    """
    path = safe_join(target_dir, "sections", f"{name}.json")
    raw = canonical_json_bytes(payload)
    if len(raw) > MAX_SECTION_BYTES:
        raise ValueError(f"section {name} 超过 {MAX_SECTION_BYTES} 字节上限")
    atomic_write_json(path, payload)
    return SectionEntry(
        name=str(name),
        schema_version=int(schema_version),
        sha256=sha256_bytes(raw),
        bytes=len(raw),
        kind=kind,
        reference_only=reference_only,
    )


def verify_revision_dir(rev_dir: str) -> Tuple[bool, RejectCode, str, List[str]]:
    """发布/恢复前重读校验。**只读**，不改任何东西。

    校验项：manifest 存在且合法 → status 是 committed →
    每个 section 文件存在、字节数一致、sha256 一致。

    为什么必须重读：manifest 里的 hash 是**写入时期望值**，
    磁盘上的实际内容可能被截断、被别的进程改过、或者根本没落盘。
    只信 manifest 就等于没校验。
    """
    warnings: List[str] = []
    mpath = manifest_path(rev_dir)
    if not os.path.isfile(mpath):
        return False, RejectCode.MISSING_FIELD, "manifest.json 不存在", warnings

    try:
        raw = read_json(mpath)
    except Exception:  # noqa: BLE001
        return False, RejectCode.IO_ERROR, "manifest.json 无法解析", warnings

    manifest, code, msg = validate_manifest(raw)
    if manifest is None:
        return False, code, msg, warnings

    if not manifest.committed:
        return False, RejectCode.NOT_COMMITTED, (
            f"revision {manifest.revision} 状态为 {manifest.status}，不是 committed"
        ), warnings

    if manifest.level_is_overstated():
        warnings.append(
            f"声明等级 {manifest.consistency_level} 与实际不符"
            f"（含引用型 section），实际为 {manifest.effective_level().value}"
        )

    sdir = sections_dir(rev_dir)
    for entry in manifest.sections:
        path = os.path.join(sdir, f"{entry.name}.json")
        if not os.path.isfile(path):
            return False, RejectCode.SECTION_MISSING, (
                f"section 文件缺失: {entry.name}"
            ), warnings
        actual_size = file_size(path)
        if actual_size != entry.bytes:
            return False, RejectCode.SECTION_HASH_MISMATCH, (
                f"section {entry.name} 字节数不符"
                f"（期望 {entry.bytes}，实际 {actual_size}）"
            ), warnings
        try:
            actual_hash = sha256_file(path)
        except OSError:
            return False, RejectCode.IO_ERROR, f"section {entry.name} 无法读取", warnings
        if actual_hash != entry.sha256:
            return False, RejectCode.SECTION_HASH_MISMATCH, (
                f"section {entry.name} 内容校验失败"
            ), warnings

    return True, RejectCode.OK, "", warnings


# ─────────────────────────────────────────────────────────────
# 发布（B1-02）
# ─────────────────────────────────────────────────────────────


def publish_revision(
    root: str,
    slot_id: str,
    staging: str,
    revision: str,
    *,
    parent_revision: str = "",
    update_pointer: bool = True,
) -> Tuple[Optional[SnapshotManifest], RejectCode, str]:
    """把 staging 目录发布成正式 revision。

    流程（GameSaveArchitecture §5 步骤 5–6）：

    1. 重读 staging 里的 manifest 并校验 section hash；
    2. 把 status 翻成 `committed`（在 staging 内改写，不碰已发布数据）；
    3. `atomic_publish_dir()` 原子 rename 到 `snapshots/<revision>`；
    4. 原子写 `current.json` 指针。

    故障语义（B1-02 验收）
    ─────────────────────
    * 第 1 步失败：staging 保留，旧 current **完全不变**；
    * 第 3 步前崩溃：staging 不是有效 revision，旧 current 不变；
    * 第 3 步成功、第 4 步失败：revision 已发布但指针未更新，
      可按 `operation_id` 查询后补指，**不会重复生成同一 revision**
      （目标已存在时 `atomic_publish_dir` 直接拒绝）。

    目标 revision 已存在时**拒绝覆盖**：committed revision 不得原地编辑。
    """
    try:
        target = revision_dir(root, slot_id, revision)

        if os.path.exists(target):
            return None, RejectCode.REVISION_EXISTS, (
                f"revision {revision} 已存在，拒绝覆盖"
            )

        mpath = manifest_path(staging)
        if not os.path.isfile(mpath):
            return None, RejectCode.MISSING_FIELD, "staging 缺少 manifest.json"

        manifest, code, msg = validate_manifest(read_json(mpath))
        if manifest is None:
            return None, code, msg

        # 2) 翻状态
        committed = manifest.with_status(RevisionStatus.COMMITTED)
        atomic_write_json(mpath, committed.to_dict())

        # 1') 翻状态后重新校验（此时 status 才是 committed）
        ok, code, msg, _ = verify_revision_dir(staging)
        if not ok:
            return None, code, msg

        # 3) 原子发布
        atomic_publish_dir(staging, target)

        # 4) 原子更新指针
        if update_pointer:
            atomic_write_json(current_pointer_path(root, slot_id), {
                "revision": committed.revision,
                "slot_id": committed.slot_id,
                "updated_at": committed.created_at,
                "consistency_level": committed.effective_level().value,
            })

        return committed, RejectCode.OK, ""
    except FileExistsError as exc:
        return None, RejectCode.REVISION_EXISTS, str(exc)
    except OSError as exc:
        return None, RejectCode.IO_ERROR, f"发布失败: {exc}"
    except ValueError as exc:
        # safe_join 的路径逃逸
        return None, RejectCode.PATH_ESCAPE, str(exc)


def read_current(root: str, slot_id: str) -> Tuple[Optional[SnapshotManifest], RejectCode, str]:
    """读当前有效 revision（指针 → manifest → 校验）。

    指针**指向不等于有效**：这里仍会重读校验，
    否则被手工改过的指针能把 staging 目录当成正式快照。
    """
    pointer = current_pointer_path(root, slot_id)
    if not os.path.isfile(pointer):
        return None, RejectCode.NO_CURRENT, "没有 current.json 指针"
    try:
        raw = read_json(pointer)
    except Exception:  # noqa: BLE001
        return None, RejectCode.IO_ERROR, "current.json 无法解析"

    revision = str((raw or {}).get("revision", "") or "")
    if not _REVISION_RE.match(revision):
        return None, RejectCode.BAD_REVISION, f"指针里的 revision 非法: {revision!r}"

    return read_revision(root, slot_id, revision)


def read_revision(
    root: str, slot_id: str, revision: str
) -> Tuple[Optional[SnapshotManifest], RejectCode, str]:
    """读并校验一个已发布 revision。"""
    target = revision_dir(root, slot_id, revision)
    ok, code, msg, _ = verify_revision_dir(target)
    if not ok:
        return None, code, msg
    try:
        raw = read_json(manifest_path(target))
    except Exception:  # noqa: BLE001
        return None, RejectCode.IO_ERROR, "manifest 无法解析"
    manifest, code, msg = validate_manifest(raw)
    if manifest is None:
        return None, code, msg
    return manifest, RejectCode.OK, ""


def list_revisions(root: str, slot_id: str) -> List[Dict[str, Any]]:
    """列出槽下所有 revision（**不校验**，列表展示用）。

    列表要快，且不能因为某个 revision 损坏就让整页打不开。
    是否可恢复由 `preview_restore()` 单独判断。
    """
    base = snapshots_dir(root, slot_id)
    if not os.path.isdir(base):
        return []
    out: List[Dict[str, Any]] = []
    for name in sorted(os.listdir(base)):
        mpath = os.path.join(base, name, "manifest.json")
        if not os.path.isfile(mpath):
            out.append({"revision": name, "readable": False, "reason": "manifest 缺失"})
            continue
        try:
            raw = read_json(mpath)
        except Exception:  # noqa: BLE001
            out.append({"revision": name, "readable": False, "reason": "manifest 损坏"})
            continue
        manifest, code, _ = validate_manifest(raw)
        if manifest is None:
            out.append({"revision": name, "readable": False, "reason": code.value})
            continue
        out.append({
            "revision": name,
            "readable": True,
            "status": manifest.status,
            "consistency_level": manifest.effective_level().value,
            "created_at": manifest.created_at,
            "sections": sorted(s.name for s in manifest.sections),
            "parent_revision": manifest.parent_revision,
            "branch_id": manifest.branch_id,
            "label": manifest.label,
            "trigger": manifest.trigger,
        })
    return out


# ─────────────────────────────────────────────────────────────
# 恢复预演（B1-03）
# ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RestorePlan:
    """恢复计划。**只读产物**：生成过程不改任何运行态。

    §6 Preview 阶段的要求：校验 manifest、hash、大小、schema、
    资源与路径边界，回答"会覆盖什么、缺什么、要不要迁移"，
    **不创建/删除角色，不清理记忆**。
    """

    slot_id: str = ""
    revision: str = ""
    #: 是否可以安全执行
    safe: bool = False
    code: RejectCode = RejectCode.OK
    message: str = ""
    consistency_level: str = ""
    #: 将被覆盖的领域（按应用顺序）
    targets: Tuple[str, ...] = ()
    #: 需要的迁移动作
    migrations: Tuple[Tuple[str, str], ...] = ()
    #: 缺失的 section / artifact
    missing: Tuple[str, ...] = ()
    #: 非阻断但值得告知的问题
    warnings: Tuple[str, ...] = ()
    #: S2-04：回档对记忆的影响（MementoMemoryIntegration §4）。
    #: **只读产物**：文件层能确定的部分在这里算，
    #: 运行态部分（快照之后新增/删除的条数）由注入的 probe 提供。
    memory_impact: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "slot_id": self.slot_id,
            "revision": self.revision,
            "safe": self.safe,
            "code": self.code.value,
            "message": self.message,
            "consistency_level": self.consistency_level,
            "targets": list(self.targets),
            "migrations": [{"section": s, "action": a} for s, a in self.migrations],
            "missing": list(self.missing),
            "warnings": list(self.warnings),
            "memory_impact": dict(self.memory_impact),
        }


def preview_restore(
    root: str,
    slot_id: str,
    revision: str = "",
    *,
    memory_probe: Optional[Any] = None,
) -> RestorePlan:
    """生成恢复计划。**只读**，绝不改运行态。"""
    try:
        revision_dir(root, slot_id, revision or "rev-000000")
    except ValueError as exc:
        return RestorePlan(
            slot_id=str(slot_id), revision=str(revision),
            safe=False, code=RejectCode.PATH_ESCAPE, message=str(exc),
        )

    resolved = revision
    if not resolved:
        current, code, msg = read_current(root, slot_id)
        if current is None:
            return RestorePlan(
                slot_id=str(slot_id), safe=False, code=code, message=msg,
            )
        resolved = current.revision

    # 解析完 current 之后再算真实目录
    try:
        rev_dir = revision_dir(root, slot_id, resolved)
    except ValueError as exc:
        return RestorePlan(
            slot_id=str(slot_id), revision=resolved,
            safe=False, code=RejectCode.PATH_ESCAPE, message=str(exc),
        )

    manifest, code, msg = read_revision(root, slot_id, resolved)
    if manifest is None:
        return RestorePlan(
            slot_id=str(slot_id), revision=resolved,
            safe=False, code=code, message=msg,
        )

    warnings: List[str] = list()
    missing: List[str] = []
    migrations: List[Tuple[str, str]] = []

    ok, vcode, vmsg, vwarnings = verify_revision_dir(rev_dir)
    warnings.extend(vwarnings)
    if not ok:
        return RestorePlan(
            slot_id=str(slot_id), revision=resolved,
            safe=False, code=vcode, message=vmsg,
            consistency_level=manifest.consistency_level,
            warnings=tuple(warnings),
        )

    present = manifest.section_map
    targets: List[str] = []

    for name in RESTORE_ORDER:
        owner = SECTION_OWNERS.get(name, name)
        if name in present:
            entry = present[name]
            targets.append(owner)
            if entry.schema_version > SECTION_SCHEMA_VERSION:
                # 不能降级：应用读不懂更新的 DTO
                return RestorePlan(
                    slot_id=str(slot_id), revision=resolved, safe=False,
                    code=RejectCode.UNSUPPORTED_SCHEMA,
                    message=f"section {name} schema {entry.schema_version} "
                            f"高于当前 {SECTION_SCHEMA_VERSION}，无法降级",
                    consistency_level=manifest.consistency_level,
                    targets=tuple(targets), warnings=tuple(warnings),
                )
            if entry.schema_version < SECTION_SCHEMA_VERSION:
                migrations.append((name, MigrationAction.UPGRADE_SECTION.value))
            else:
                migrations.append((name, MigrationAction.NONE.value))
        else:
            missing.append(name)
            migrations.append((name, MigrationAction.SECTION_ABSENT.value))

    # manifest 里有、但不在已知归属表里的 section：照单收下但告警
    for entry in manifest.sections:
        if entry.name not in SECTION_OWNERS:
            warnings.append(f"未知 section: {entry.name}（将按原样保留，不应用）")

    level = manifest.effective_level()
    if manifest.level_is_overstated():
        warnings.append(
            f"快照声明 {manifest.consistency_level}，实际只有 {level.value}"
        )
    if level in (ConsistencyLevel.METADATA, ConsistencyLevel.CHECKPOINT):
        warnings.append(
            f"该快照为 {level.value} 级，恢复后部分历史/记忆可能不是快照当时的状态"
        )
    if manifest.has_reference_only:
        warnings.append("快照含引用型 section，引用目标可能已变化")

    impact = _memory_impact_from_sections(rev_dir, manifest)
    if memory_probe is not None:
        try:
            probe = memory_probe(manifest) or {}
            if isinstance(probe, dict):
                impact.update({
                    "will_discard_created_after": probe.get(
                        "will_discard_created_after"),
                    "tombstones_to_replay": probe.get("tombstones_to_replay"),
                    "clock": probe.get("clock"),
                })
                impact.pop("probe_missing", None)
        except Exception:  # noqa: BLE001
            # 探针失败不能让预览失败：预览是只读的，降级为"信息不全"
            warnings.append("记忆运行态探针不可用，影响预览中的数量信息")
    if impact.get("probe_missing"):
        warnings.append("未提供运行态探针，回档预览不含'将丢弃的记忆条数'")

    return RestorePlan(
        slot_id=str(slot_id),
        revision=resolved,
        safe=True,
        code=RejectCode.OK,
        message="预演通过",
        consistency_level=level.value,
        targets=tuple(dict.fromkeys(targets)),
        migrations=tuple(migrations),
        missing=tuple(missing),
        warnings=tuple(warnings),
        memory_impact=impact,
    )


def _memory_impact_from_sections(
    rev_dir: str, manifest: "SnapshotManifest"
) -> Dict[str, Any]:
    """从快照文件里提取**文件层能确定**的记忆影响（只读）。

    不连数据库：SQLite 是运行态，文件层只认自己写过的 section。
    """
    impact: Dict[str, Any] = {
        "will_restore": 0,
        "will_discard_created_after": None,
        "tombstones_to_replay": None,
        "strength_schema": 1,
        "clock": None,
        "probe_missing": True,
    }
    sections = manifest.section_map
    strength = sections.get("memory-strength")
    if strength is not None:
        try:
            raw = read_json(safe_join(rev_dir, "sections", "memory-strength.json"))
        except Exception:  # noqa: BLE001
            raw = None
        if isinstance(raw, dict):
            try:
                impact["will_restore"] = int(raw.get("row_count", 0) or 0)
            except (TypeError, ValueError):
                pass
            try:
                impact["strength_schema"] = int(
                    raw.get("schema_version", strength.schema_version) or 1
                )
            except (TypeError, ValueError):
                pass
    else:
        impact["strength_schema"] = None

    clock_entry = sections.get("memory-clock")
    if clock_entry is not None:
        try:
            raw = read_json(safe_join(rev_dir, "sections", "memory-clock.json"))
        except Exception:  # noqa: BLE001
            raw = None
        if isinstance(raw, dict):
            clock = raw.get("clock")
            if isinstance(clock, dict):
                impact["clock"] = {
                    "kind": str(clock.get("kind", "wall")),
                    "anchor_day": float(clock.get("anchor_day", 0.0) or 0.0),
                    "active_days": float(clock.get("active_seconds", 0.0) or 0.0)
                    / 86400.0,
                    "game_day": float(clock.get("game_day", 0.0) or 0.0),
                }
    return impact

def revision_graph(root: str, slot_id: str) -> Dict[str, Any]:
    """把 revision 列表组织成 DAG（MementoMemoryIntegration）"""
    items = list_revisions(root, slot_id)
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, str]] = []
    by_revision = {str(x.get("revision", "")): x for x in items}
    children: Dict[str, List[str]] = {}

    for item in items:
        rev = str(item.get("revision", ""))
        parent = str(item.get("parent_revision", "") or "")
        nodes.append({
            "revision": rev,
            "parent": parent,
            "branch_id": str(item.get("branch_id", "main") or "main"),
            "label": str(item.get("label", "") or ""),
            "trigger": str(item.get("trigger", "manual") or "manual"),
            "created_at": item.get("created_at", ""),
            "readable": bool(item.get("readable", False)),
            "reason": item.get("reason", ""),
        })
        if parent and parent in by_revision:
            edges.append({"from": parent, "to": rev})
            children.setdefault(parent, []).append(rev)
        elif parent:
            # 父 revision 已被 GC：仍记边，但标明悬空，避免假装是根节点
            edges.append({"from": parent, "to": rev, "dangling": True})

    heads = [rev for rev in by_revision if rev not in children]
    branches: Dict[str, List[str]] = {}
    for node in nodes:
        branches.setdefault(node["branch_id"], []).append(node["revision"])

    current, _, _ = read_current(root, slot_id)
    return {
        "slot_id": str(slot_id),
        "nodes": nodes,
        "edges": edges,
        "branches": {k: sorted(v) for k, v in branches.items()},
        "heads": sorted(heads),
        "current": current.revision if current else "",
        "protected": current.revision if current else "",
    }


def descendants(root: str, slot_id: str, revision: str) -> List[str]:
    """某 revision 的所有后代（删除分支前检查是否为唯一恢复点用）。"""
    graph = revision_graph(root, slot_id)
    children: Dict[str, List[str]] = {}
    for edge in graph["edges"]:
        children.setdefault(edge["from"], []).append(edge["to"])
    out: List[str] = []
    stack = list(children.get(str(revision), []))
    seen = set()
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        out.append(node)
        stack.extend(children.get(node, []))
    return sorted(out)


def is_safe_path(root: str, path: str) -> bool:
    """外部导入的存档包解压前用：路径必须在 root 内。"""
    return is_within(root, path)
