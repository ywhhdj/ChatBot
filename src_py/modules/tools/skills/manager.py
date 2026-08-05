from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, Optional, Set
import yaml
from ...manager.task.decorator import sync_task_scheduler
from ...logger import logger
from .sandbox import RestrictedCodeExecutor
from .models import ExternalSkill, ExternalSkillMetadata, SkillsManagerConfig

class ExternalSkillManager:
    _instance = None
    _skills: Dict[str, ExternalSkill] = {}
    _pending_activation: Set[str] = set()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self) -> None:
        self._executor = RestrictedCodeExecutor()
        self._config = SkillsManagerConfig(
            skill_dir="skills"
        )
        self.load_from_directory(self._config.skill_dir)

    @sync_task_scheduler
    def load_from_directory(self, directory: str) -> None:
        dir_path = Path(directory)
        if not dir_path.exists():
            return
        for file_path in dir_path.rglob("SKILL.md"):
            self._load_single_file(file_path)

    def _load_single_file(self, file_path: Path) -> None:
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning(f"Failed to read skill {file_path}: {exc}")
            return
        if not content.startswith("---"):
            return
        parts = content.split("---", 2)
        if len(parts) < 3:
            return
        try:
            raw_meta = yaml.safe_load(parts[1]) or {}
            metadata = ExternalSkillMetadata(
                name=str(raw_meta.get("name", "")).strip(),
                description=str(raw_meta.get("description", "")).strip(),
                license=str(raw_meta.get("license", "MIT")),
                version=str(raw_meta.get("version", "1.0.0")),
                author=str(raw_meta.get("author", "")),
            )
        except Exception as exc:
            logger.warning(f"Invalid skill metadata {file_path}: {exc}")
            return

        ok, errors = metadata.validate()
        if not ok:
            logger.warning(f"Invalid skill {file_path}: {'; '.join(errors)}")
            return

        execution = raw_meta.get("execution") or {}
        exec_type = execution.get("type", "python")
        code = execution.get("code", "")
        if not code:
            code = parts[2].strip()
        skill = ExternalSkill(metadata.name, metadata, code, exec_type)
        self._skills[metadata.name] = skill
        self._pending_activation.add(metadata.name)

    def activate_skill(self, name: str) -> bool:
        skill = self._skills.get(name)
        if not skill:
            return False
        skill.active = True
        self._pending_activation.discard(name)
        return True

    def deactivate_skill(self, name: str) -> bool:
        skill = self._skills.get(name)
        if not skill:
            return False
        skill.active = False
        return True

    def reject_skill(self, name: str) -> bool:
        self._pending_activation.discard(name)
        self._skills.pop(name, None)
        return True

    def get_active_skills(self) -> Dict[str, ExternalSkill]:
        return {name: skill for name, skill in self._skills.items() if skill.active}

    def get_pending_skills(self) -> Dict[str, str]:
        return {
            name: skill.get_description()
            for name, skill in self._skills.items()
            if name in self._pending_activation
        }

    def get_skill(self, name: str) -> Optional[ExternalSkill]:
        return self._skills.get(name)

    def list_skills(self, active_only: bool = False) -> Dict[str, str]:
        items = self.get_active_skills() if active_only else self._skills
        return {name: skill.get_description() for name, skill in items.items()}

    def build_prompt(self) -> str:
        skills = self.list_skills(active_only=False)
        if not skills:
            return ""
        lines = [
            "## 可用 Skills", 
            "只在需要技能时输出: skill --name <name> --des \"<需求描述>\""
        ]
        for name, description in skills.items():
            lines.append(f"skill --name {name} --des \"{description}\"")
        return "\n".join(lines)

    async def execute_skill(self, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        skill = self._skills.get(name)
        if not skill:
            return {"ok": False, "error": f"未知 skill: {name}"}
        if not skill.active:
            self.activate_skill(name)
        if skill.exec_type == "python":
            
            context = {
                "input_data": params, 
                "params": params, 
                "result": None
            }
            return await self._executor.execute(skill.code, context=context)
        if skill.exec_type == "api":
            return {
                "ok": False, 
                "error": "api skill 尚未实现"
            }
        if skill.exec_type == "shell":
            return {
                "ok": False, 
                "error": "shell skill 默认禁用，请改为 python 沙盒实现"
            }
        return {
            "ok": False, 
            "error": f"不支持的 skill 类型: {skill.exec_type}"
        }
