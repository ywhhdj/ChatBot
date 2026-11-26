"""技能数据模型"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Tuple


class ExecType(str, Enum):
    NONE = "none"            # 无脚本，仅作为提示/上下文
    PYTHON = "python"        # Python 沙盒执行
    SHELL = "shell"          # Shell —— 明确拒绝执行
    JAVASCRIPT = "javascript"

    @classmethod
    def from_suffix(cls, suffix: str) -> "ExecType":
        return {
            ".py": cls.PYTHON,
            ".sh": cls.SHELL,
            ".js": cls.JAVASCRIPT,
        }.get(suffix.lower(), cls.NONE)


@dataclass
class SkillMetadata:
    name: str
    description: str
    license: str = ""
    version: str = "1.0.0"
    author: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def validate(self) -> Tuple[bool, List[str]]:
        import re

        errors: List[str] = []
        if not self.name:
            errors.append("name 不能为空")
        elif not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", self.name):
            errors.append(
                f"name '{self.name}' 格式错误：必须是小写字母+连字符，如 'code-review'"
            )
        elif len(self.name) > 64:
            errors.append(f"name '{self.name}' 超过 64 字符限制")
        if not self.description:
            errors.append("description 不能为空")
        elif len(self.description) > 1024:
            errors.append("description 超过 1024 字符限制")
        return len(errors) == 0, errors


@dataclass
class PendingInfo:
    """待审批技能的结构化元数据"""

    reason: str = "new_skill"
    source: str = "filesystem"
    discovered_at: float = 0.0
    requested_by: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> "PendingInfo":
        d = data if isinstance(data, dict) else {}
        try:
            ts = float(d.get("discovered_at", 0.0) or 0.0)
        except (TypeError, ValueError):
            ts = 0.0
        return cls(
            reason=str(d.get("reason") or "new_skill"),
            source=str(d.get("source") or "filesystem"),
            discovered_at=ts,
            requested_by=str(d.get("requested_by") or ""),
        )


def _type_matches(value: Any, expected: str) -> bool:
    expected = str(expected or "").lower()
    if not expected or expected == "any":
        return True
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, (list, tuple))
    if expected == "object":
        return isinstance(value, dict)
    if expected == "null":
        return value is None
    return True   # 未知类型声明不做拦截，交由 validate_skill() 报 schema 错误


@dataclass
class Skill:
    metadata: SkillMetadata
    exec_type: ExecType = ExecType.NONE
    active: bool = True
    #: 待审批。与 active 正交：pending 技能 active 恒为 False。
    pending: bool = False
    #: 惰性加载的可执行代码（不进索引）
    code: str = ""
    #: SKILL.md 除 frontmatter 外的正文（不进索引）
    context: str = ""
    #: 脚本文件名（进索引，供惰性补载定位）
    entry: str = ""
    #: 代码是否已从磁盘补载（运行时标记，不进索引）
    code_loaded: bool = False
    #: 参数 schema：{"required": [...], "properties": {name: {"type": ...}}}
    params_schema: Dict[str, Any] = field(default_factory=dict)

    @property
    def description(self) -> str:
        return self.metadata.description

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def supported(self) -> bool:
        return self.exec_type == ExecType.PYTHON

    def to_dict(self) -> Dict[str, Any]:
        """索引形态：**不含 code / context**。"""
        data = self.metadata.to_dict()
        data.update({
            "active": bool(self.active),
            "pending": bool(self.pending),
            "exec_type": (
                self.exec_type.value
                if isinstance(self.exec_type, ExecType)
                else str(self.exec_type)
            ),
            "entry": str(self.entry or ""),
            "params_schema": dict(self.params_schema or {}),
        })
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Skill":
        payload = dict(data or {})
        meta_fields = {"name", "description", "license", "version", "author"}
        meta_kwargs = {k: v for k, v in payload.items() if k in meta_fields}
        raw_type = str(payload.get("exec_type", "none") or "none")
        try:
            exec_type = ExecType(raw_type)
        except ValueError:
            exec_type = ExecType.NONE
        schema = payload.get("params_schema")
        return cls(
            metadata=SkillMetadata(**meta_kwargs),
            exec_type=exec_type,
            active=bool(payload.get("active", True)),
            pending=bool(payload.get("pending", False)),
            entry=str(payload.get("entry", "") or ""),
            params_schema=dict(schema) if isinstance(schema, dict) else {},
        )

    def validate_params(self, params: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """按 SKILL.md 声明的 schema 校验执行参数。

        只做必填 + 顶层类型，不查额外字段：`ctl.py` 会把 `--id` / `--des`
        一起放进 params，禁止额外字段会把整条命令链打断。
        """
        schema = self.params_schema or {}
        if not isinstance(schema, dict) or not schema:
            return True, []
        if not isinstance(params, dict):
            return False, ["params 必须是对象"]
        errors: List[str] = []
        required = schema.get("required") or []
        if isinstance(required, (list, tuple)):
            for key in required:
                if str(key) not in params:
                    errors.append(f"缺少必填参数: {key}")
        props = schema.get("properties") or {}
        if isinstance(props, dict):
            for key, spec in props.items():
                if key not in params:
                    continue
                expected = spec.get("type") if isinstance(spec, dict) else str(spec)
                if not _type_matches(params[key], str(expected or "")):
                    errors.append(
                        f"参数 {key} 类型不符: 需要 {expected}，"
                        f"实际 {type(params[key]).__name__}"
                    )
        return len(errors) == 0, errors


@dataclass
class SkillsManagerConfig:
    skill_dir: Path = field(default_factory=lambda: Path("skills"))
