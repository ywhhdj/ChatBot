"""领域快照 Originator 契约（B1-03 剩余 / S2-01 前置）。

依据 `GameSaveArchitecture.md` §2 / §6 与
`MementoMemoryIntegration.md` §2.1。

为什么先定契约再写实现
──────────────────────
前几轮 B1-03 只做了 `preview_restore()`，Prepare/Commit/Rollback
一直没动，原因写进了 PLAN.md §6："需各 originator 提供 restore 接口"。
本文件把那个接口**定死**，让 Caretaker 与领域实现可以并行落地，
而不是把半成品散在各处。

四阶段语义（§6）
────────────────
| 阶段 | 允许做什么 | 禁止做什么 |
|---|---|---|
| `export_snapshot` | 事务读快照 / 水位，产出版本化 DTO | 不读私有变量、不导出 lock/provider/loop |
| `prepare_restore` | 载入**临时对象**、校验 schema 与业务不变量 | 不改运行态、不暴露部分恢复状态 |
| `commit_restore` | 在恢复锁内原子替换 staged state | 不调 UI / EventBus / LLM |
| `rollback_restore` | 用保护快照还原 | 不谎报成功 |

`commit_restore` 必须**可补偿**：协调器按 `RESTORE_ORDER` 顺序提交，
中途某域失败时，对已提交的域按逆序调 `rollback_restore()`。
因此每个 originator 的 `prepare_restore()` 必须保存 enough state
让 rollback 能独立工作 —— 不能依赖"上一个域的暂存对象还在"。

依赖方向
────────
本文件只依赖标准库；`memento.py` 的文件层类型通过
`TYPE_CHECKING` 引用，避免契约层反向依赖文件层。
具体领域实现（MemoryOriginator 等）单向实现这里的 Protocol。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Protocol, Sequence, Tuple, runtime_checkable


class PrepareReject(str, Enum):
    """Prepare 阶段的稳定拒绝码（不含自由文本，便于前端与审计）。"""

    OK = "ok"
    UNSUPPORTED_SCHEMA = "unsupported_schema"
    MISSING_SECTION = "missing_section"
    HASH_MISMATCH = "hash_mismatch"
    FOREIGN_KEY = "foreign_key"
    INVALID_VALUE = "invalid_value"
    TIME_TRAVEL = "time_travel"
    CONFLICT = "conflict"
    IO_ERROR = "io_error"


class SnapshotTrigger(str, Enum):
    """存档触发类型（`MementoMemoryIntegration.md` §5 / §6）。"""

    MANUAL = "manual"
    QUICK = "quick"
    AUTO = "auto"
    PRE_RESTORE = "pre-restore"
    PRE_MIGRATION = "pre-migration"


@dataclass(frozen=True)
class SnapshotContext:
    """`export_snapshot` 的上下文。**只读**。"""

    slot_id: str = ""
    revision: str = ""
    operation_id: str = ""
    branch_id: str = "main"
    label: str = ""
    trigger: str = SnapshotTrigger.MANUAL.value
    #: 一致性水位：各域只导出 <= 该水位的已提交数据
    watermark: float = 0.0
    #: 冻结边界时刻（epoch 秒）
    captured_at: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "slot_id": self.slot_id,
            "revision": self.revision,
            "operation_id": self.operation_id,
            "branch_id": self.branch_id,
            "label": self.label,
            "trigger": self.trigger,
            "watermark": self.watermark,
            "captured_at": self.captured_at,
        }


@dataclass(frozen=True)
class SnapshotSection:
    """一个领域产出的快照 section。

    `payload` 必须是 **json 可序列化**的纯数据；调用方会做
    `canonical_json_bytes` 后写盘并记 sha256。绝不传对象引用。
    """

    name: str
    schema_version: int = 1
    payload: Dict[str, Any] = field(default_factory=dict)
    #: 是否只含引用/路径指针（会拉低 consistency_level）
    reference_only: bool = False
    #: 领域自己的水位（例如最后一个记忆版本号、最后一条消息序号）
    watermark: float = 0.0
    #: 非阻断提示，写进 RestorePlan.warnings
    warnings: Tuple[str, ...] = ()

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "schema_version": self.schema_version,
            "payload": dict(self.payload),
            "reference_only": self.reference_only,
            "watermark": self.watermark,
            "warnings": list(self.warnings),
        }


@dataclass
class PreparedRestore:
    """`prepare_restore` 的产物。**只含临时对象**，运行态未变。

    `state` 由 originator 自己定义（比如内存里的行列表、
    临时目录路径），协调器不解释它，只在 commit/rollback 时原样传回。
    这样契约层不需要知道任何领域的数据结构。
    """

    owner: str
    ok: bool = False
    code: PrepareReject = PrepareReject.OK
    message: str = ""
    #: 本域负责的 section 名
    sections: Tuple[str, ...] = ()
    #: 领域暂存数据
    state: Any = None
    #: 业务不变量校验结果，写进事务报告
    checks: Dict[str, Any] = field(default_factory=dict)
    warnings: Tuple[str, ...] = ()

    def as_dict(self) -> Dict[str, Any]:
        # **不序列化 state**：可能含连接、锁或大量数据，
        # 报告只给可解释的元信息（SecurityAndAuditDesign §5）
        return {
            "owner": self.owner,
            "ok": self.ok,
            "code": self.code.value,
            "message": self.message,
            "sections": list(self.sections),
            "checks": dict(self.checks),
            "warnings": list(self.warnings),
        }


class RestorePhase(str, Enum):
    PREVIEW = "preview"
    PREPARE = "prepare"
    COMMIT = "commit"
    VERIFY = "verify"
    ROLLBACK = "rollback"


@runtime_checkable
class Originator(Protocol):
    """领域快照接口（GameSaveArchitecture §2 / MementoMemoryIntegration §2.1）。"""

    @property
    def owner(self) -> str: ...

    @property
    def section_names(self) -> Tuple[str, ...]: ...

    def export_snapshot(self, ctx: "SnapshotContext") -> List[SnapshotSection]: ...

    def prepare_restore(self, sections: Sequence[SnapshotSection],
                        plan: Any) -> PreparedRestore: ...

    def commit_restore(self, prepared: PreparedRestore) -> None: ...

    def rollback_restore(self, prepared: PreparedRestore) -> None: ...

    def verify_restore(self, prepared: PreparedRestore) -> Tuple[bool, str]: ...


class NullOriginator:
    """缺省实现：只校验 section 结构，不碰运行态。

    用于**缺少 adapter 的域**（GameSaveArchitecture §9 第 4 条）：
    不能默认为已完整导出，必须在 manifest 里标记缺失。
    也让协调器在没有注册任何域时仍可跑通全流程做故障注入。
    """

    def __init__(self, owner: str, section_names: Sequence[str] = ()) -> None:
        self._owner = str(owner)
        self._sections = tuple(str(s) for s in section_names)

    @property
    def owner(self) -> str:
        return self._owner

    @property
    def section_names(self) -> Tuple[str, ...]:
        return self._sections

    def export_snapshot(self, ctx: "SnapshotContext") -> List[SnapshotSection]:
        return [
            SnapshotSection(
                name=name, schema_version=1, payload={},
                reference_only=True,
                warnings=(f"{self._owner}: 未注册 originator，section 仅占位",),
            )
            for name in self._sections
        ]

    def prepare_restore(self, sections, plan) -> PreparedRestore:
        return PreparedRestore(
            owner=self._owner, ok=True,
            code=PrepareReject.OK,
            message="无 originator，运行态保持不变",
            sections=tuple(s.name for s in sections),
            warnings=("该域未参与本次恢复",),
        )

    def commit_restore(self, prepared: PreparedRestore) -> None:
        return

    def rollback_restore(self, prepared: PreparedRestore) -> None:
        return

    def verify_restore(self, prepared: PreparedRestore) -> Tuple[bool, str]:
        return True, ""


def section_bytes(section: SnapshotSection) -> bytes:
    """给文件层算 hash 用的规范字节。

    与 `memento.write_section` 用**同一个** canonical 函数，
    否则 prepare 阶段算出的 hash 与文件层对不上（表现为
    "预览通过但 Prepare 每次都报 hash 不符"）。
    """
    from ...utils.file.atomic import canonical_json_bytes

    return canonical_json_bytes(section.payload)
