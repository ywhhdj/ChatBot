"""技能数据模型"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Tuple


class ExecType(str, Enum):
    NONE = "none"            # 无脚本，仅作为提示/上下文
    PYTHON = "python"        # Python 沙盒执行
    SHELL = "shell"          # Shell —— 暂不支持
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
            errors.append("name不能为空")
        elif not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", self.name):
            errors.append(f"name '{self.name}' 格式错误：必须是小写字母+连字符，如 'code-review'")
        elif len(self.name) > 64:
            errors.append(f"name '{self.name}' 超过64字符限制")
        if not self.description:
            errors.append("description不能为空")
        elif len(self.description) > 1024:
            errors.append("description超过1024字符限制")
        return len(errors) == 0, errors


@dataclass
class Skill:
    metadata: SkillMetadata
    exec_type: ExecType = ExecType.NONE
    active: bool = True
    # C80：真正承载可执行代码；由 manager 在加载时填充
    code: str = ""
    # 技能自带的说明正文（SKILL.md 除 frontmatter 外的部分），作为上下文注入
    context: str = ""
    # 脚本文件名，便于日志/报错定位
    entry: str = ""

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
        data = self.metadata.to_dict()
        data.update({
            "active": self.active,
            "exec_type": self.exec_type.value
            if isinstance(self.exec_type, ExecType)
            else str(self.exec_type),
        })
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Skill":
        payload = dict(data or {})
        meta_fields = {
            "name",
            "description",
            "license",
            "version",
            "author"
        }
        meta_kwargs = {k: v for k, v in payload.items() if k in meta_fields}
        raw_type = str(payload.get("exec_type", "none") or "none")
        try:
            exec_type = ExecType(raw_type)
        except ValueError:
            exec_type = ExecType.NONE
        return cls(
            metadata=SkillMetadata(**meta_kwargs),
            exec_type=exec_type,
            active=bool(payload.get("active", True)),
            entry=str(payload.get("entry", "") or ""),
        )


@dataclass
class SkillsManagerConfig:
    skill_dir: Path = field(default_factory=lambda: Path("skills"))
