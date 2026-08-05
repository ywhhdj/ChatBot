from dataclasses import dataclass
import re
from typing import List, Literal, Tuple

@dataclass
class ExternalSkillMetadata:
    name: str
    description: str
    license: str = "MIT"
    version: str = "1.0.0"
    author: str = ""

    def validate(self) -> Tuple[bool, List[str]]:
        errors = []
        if not self.name:
            errors.append("name不能为空")
        elif not re.match(r'^[a-z0-9]+(-[a-z0-9]+)*$', self.name):
            errors.append(f"name '{self.name}' 格式错误：必须是小写字母+连字符，如 'code-review'")
        elif len(self.name) > 64:
            errors.append(f"name '{self.name}' 超过64字符限制")
        if not self.description:
            errors.append("description不能为空")
        elif len(self.description) > 1024:
            errors.append("description超过1024字符限制")
        return len(errors) == 0, errors

@dataclass
class ExternalSkill:
    name: str
    metadata: ExternalSkillMetadata
    code: str
    exec_type: Literal["python","shell","api"] = "python"  # 'python' | 'shell' | 'api'
    active: bool = False

    def get_description(self) -> str:
        return self.metadata.description

@dataclass
class SkillsManagerConfig:
    skill_dir: str = "skills"