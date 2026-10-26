"""外部技能管理器"""

from __future__ import annotations
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Set

from ...logger import logger
from ...runtime import RuntimePath
from ...utils.file import read_markdown, yaml 
from .models import ExecType, Skill, SkillMetadata, SkillsManagerConfig

INDEX_NAME = "index.yaml"   # C89：统一为 yaml，且读写同一个文件
SKILL_DOC_NAME = "SKILL.md"

class ExternalSkillManager:
    """外部技能管理器（线程安全单例）。"""

    _instance: Optional["ExternalSkillManager"] = None
    _cls_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        # C90：加锁。原来无锁，多线程同时首次调用会创建多个实例
        with cls._cls_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        skill_dir: Optional[Path] = None,
        config: Optional[SkillsManagerConfig] = None,
    ) -> None:
        if getattr(self, "_initialized", False):
            return

        self._lock = threading.RLock()
        self._config = config or SkillsManagerConfig(
            skill_dir=Path(skill_dir) if skill_dir else Path(RuntimePath.get_skill_dir())
        )
        self._executor = self.__build_executor()
        self._skills: Dict[str, Skill] = {}
        self._pending_activation: Set[str] = set()
        self._observer = None

        # ctl.py 会传 external_skill_dir —— 这里真正用起来（C65）
        self.load_index()
        self.watch_directory()
        self._initialized = True

    @staticmethod
    def __build_executor():
        from .sandbox import RestrictedCodeExecutor

        return RestrictedCodeExecutor()

    # ---------- 索引 ----------

    @property
    def _index_path(self) -> Path:
        return Path(self._config.skill_dir) / INDEX_NAME

    def load_index(self) -> None:
        """加载技能索引（惰性：只恢复元数据与启用状态，代码按需加载）。
        """
        try:
            index = yaml.read_yaml(self._index_path)
        except Exception as exc:
            logger.debug(f"[Skills] 读取索引失败（首次启动属正常）: {exc}")
            return
        if not isinstance(index, dict):
            logger.warning(f"[Skills] 索引格式不是对象: {self._index_path}")
            return

        loaded = 0
        with self._lock:
            for skill_id, meta in index.items():
                if not isinstance(meta, dict):
                    logger.warning(f"[Skills] 跳过格式错误的索引项: {skill_id}")
                    continue
                try:
                    skill = Skill.from_dict(meta)
                    skill.metadata.name = skill.metadata.name or str(skill_id)
                    self._skills[str(skill_id)] = skill
                    # 元数据已完整（来自索引），代码仍按需加载
                    self._pending_activation.add(str(skill_id))
                    loaded += 1
                except Exception as exc:
                    logger.warning(f"[Skills] 跳过损坏的技能 {skill_id}: {exc}")
        if loaded:
            logger.info(f"[Skills] 已加载 {loaded} 个技能索引")

    def upadate_index(self) -> None:
        self.update_index()

    def update_index(self) -> None:
        with self._lock:
            payload = {
                skill_id: skill.to_dict()
                for skill_id, skill in self._skills.items()
            }
        try:
            self._config.skill_dir.mkdir(parents=True, exist_ok=True)
            yaml.write_yaml(self._index_path, payload)
        except Exception as exc:
            logger.error(f"[Skills] 写入索引失败 {self._index_path}: {exc}")

    # ---------- 目录监听（C88） ----------

    def watch_directory(self) -> None:
        """真正启动目录监听。

        原实现只定义了一个局部 `on_event` 就返回，observer 从未创建 ——
        监听形同虚设。这里补上注册逻辑；watchdog 不可用时静默降级
        （目录监听是锦上添花，不该让它拖垮启动）。
        """
        try:
            from watchdog.events import FileSystemEventHandler # type: ignore
            from watchdog.observers import Observer # type: ignore
        except Exception:
            logger.debug("[Skills] watchdog 未安装，跳过目录监听")
            return

        manager = self

        class _Handler(FileSystemEventHandler):
            def on_created(self, event):
                # C88：src_path 是 str，不是 Path
                path = Path(str(event.src_path))
                if path.name == SKILL_DOC_NAME:
                    manager._load_single_file(path.parent.name)
                elif path.name == INDEX_NAME:
                    manager.load_index()

            def on_modified(self, event):
                path = Path(str(event.src_path))
                if path.name == INDEX_NAME:
                    manager.load_index()

        try:
            self._config.skill_dir.mkdir(parents=True, exist_ok=True)
            observer = Observer()
            observer.schedule(_Handler(), str(self._config.skill_dir), recursive=True)
            observer.daemon = True
            observer.start()
            self._observer = observer
        except Exception as exc:
            logger.warning(f"[Skills] 启动目录监听失败: {exc}")

    # ---------- 单个技能加载 ----------

    def _load_single_file(self, skill_id: str) -> None:
        """加载单个技能：解析 SKILL.md 的 frontmatter + 读取脚本代码。"""
        skill_dir = Path(self._config.skill_dir) / skill_id
        doc_path = skill_dir / SKILL_DOC_NAME
        try:
            content = read_markdown(doc_path, encoding="utf-8")
        except Exception as exc:
            logger.warning(f"[Skills] 读取技能失败 {doc_path}: {exc}")
            return
        if not content.startswith("---"):
            logger.warning(f"[Skills] {doc_path} 缺少 frontmatter，已跳过")
            return
        parts = content.split("---", 2)
        if len(parts) < 3:
            return
        try:
            raw_meta = yaml.parse_yaml(parts[1]) or {}
            if not isinstance(raw_meta, dict) or not raw_meta:
                raise ValueError("frontmatter 不是有效的 YAML 对象")
            metadata = SkillMetadata(
                name=str(raw_meta.get("name") or skill_id).strip(),
                description=str(raw_meta.get("description", "")).strip(),
                license=str(raw_meta.get("license", "MIT")),
                version=str(raw_meta.get("version", "1.0.0")),
                author=str(raw_meta.get("author", "")),
            )
        except Exception as exc:
            logger.warning(f"[Skills] 元数据解析失败 {doc_path}: {exc}")
            return

        ok, errors = metadata.validate()
        if not ok:
            logger.warning(f"[Skills] 技能 {skill_id} 校验失败: {'; '.join(errors)}")
            return

        # C93：原来传的是 file_path.parent（skills 根目录），
        # 于是 __get_exec_type 去找 skills/scripts —— 永远不存在，
        # exec_type 恒为 0(none)。这里传技能自己的目录。
        exec_type, entry, code = self._probe_scripts(skill_dir)

        with self._lock:
            skill = Skill(
                metadata=metadata,
                exec_type=exec_type,
                active=True,
                code=code,                      # C80：真正填充代码
                context=parts[2].strip(),
                entry=entry,
            )
            self._skills[skill_id] = skill
            self._pending_activation.add(skill_id)
        logger.info(f"[Skills] 已加载技能 {skill_id} (type={exec_type.value})")

    def _probe_scripts(self, skill_dir: Path):
        """探测技能脚本：返回 (exec_type, entry_name, code)。

        C94：优先级 python > javascript > shell，与"shell 不支持执行"一致 ——
        即使只有 .sh，也标记为 SHELL 并在执行时拒绝，而不是默默当 none 跳过。
        """
        scripts_dir = skill_dir / "scripts"
        if not scripts_dir.exists():
            return ExecType.NONE, "", ""

        priority = [
            (".py", ExecType.PYTHON),
            (".js", ExecType.JAVASCRIPT),
            (".sh", ExecType.SHELL)
        ]
        for suffix, exec_type in priority:
            for file in sorted(scripts_dir.iterdir()):
                if file.suffix.lower() == suffix and file.is_file():
                    code = ""
                    if exec_type == ExecType.PYTHON:
                        # 只有 python 需要读源码进沙盒
                        try:
                            code = file.read_text(encoding="utf-8")
                        except Exception as exc:
                            logger.warning(f"[Skills] 读取脚本失败 {file}: {exc}")
                    return exec_type, file.name, code
        return ExecType.NONE, "", ""

    # ---------- 启用 / 停用（C95） ----------

    def activate_skill(self, skill_id: str) -> bool:
        with self._lock:
            skill = self._skills.get(skill_id)
            if not skill:
                return False
            skill.active = True
            self._pending_activation.discard(skill_id)
        return True

    def deactivate_skill(self, skill_id: str) -> bool:
        with self._lock:
            skill = self._skills.get(skill_id)
            if not skill:
                return False
            skill.active = False
        return True

    def reject_skill(self, skill_id: str) -> bool:
        with self._lock:
            self._pending_activation.discard(skill_id)
            self._skills.pop(skill_id, None)
        return True

    # ---------- 查询 ----------

    def get_active_skills(self) -> Dict[str, Skill]:
        with self._lock:
            return {k: v for k, v in self._skills.items() if v.active}

    def get_pending_skills(self) -> Dict[str, str]:
        with self._lock:
            return {
                skill_id: skill.description
                for skill_id, skill in self._skills.items()
                if skill_id in self._pending_activation
            }

    def get_skill(self, skill_id: str) -> Optional[Skill]:
        with self._lock:
            return self._skills.get(skill_id)

    def list_skills(self, active_only: bool = False) -> Dict[str, str]:
        with self._lock:
            items = self.get_active_skills() if active_only else dict(self._skills)
        return {skill_id: skill.description for skill_id, skill in items.items()}

    # ---------- 执行 ----------

    async def execute_skill(self, skill_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行技能。

        C79：exec_type 现在是正确的 str 枚举，比较能命中。
        C80：skill.code 已被填充。
        C97：SHELL 明确不支持执行（需求），直接返回不支持，不落到默认分支。
        C95：不再"执行时自动激活"—— 待确认技能需要显式 activate，
             自动激活会让审批机制形同虚设。
        """
        with self._lock:
            skill = self._skills.get(skill_id)
        if not skill:
            return {"ok": False, "error": f"未知 skill: {skill_id}"}
        if not skill.active:
            return {"ok": False, "error": f"skill 未启用: {skill_id}"}

        if skill.exec_type == ExecType.SHELL:
            # C97：shell 类型暂不支持执行
            return {
                "ok": False,
                "error": "shell skill 暂不支持执行，请改用 python 沙盒实现",
            }
        if skill.exec_type == ExecType.JAVASCRIPT:
            return {"ok": False, "error": "javascript skill 尚未实现"}
        if skill.exec_type == ExecType.NONE:
            return {"ok": False, "error": f"skill {skill_id} 没有可执行脚本"}
        if skill.exec_type != ExecType.PYTHON:
            return {"ok": False, "error": f"不支持的 skill 类型: {skill.exec_type}"}
        if not skill.code:
            return {"ok": False, "error": f"skill {skill_id} 代码为空"}

        context = {
            "input_data": params,
            "params": params,
            "result": None,
        }
        try:
            return await self._executor.execute(skill.code, context=context)
        except Exception as exc:
            logger.error(f"[Skills] 执行 {skill_id} 失败: {exc}")
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    # ---------- 关闭 ----------

    def close(self) -> None:
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=2)
            except Exception:
                pass
            self._observer = None
        self.update_index()
        with self._lock:
            self._skills.clear()
            self._pending_activation.clear()
