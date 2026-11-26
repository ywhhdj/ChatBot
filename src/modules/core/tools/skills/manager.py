"""外部技能管理器"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ....logger import logger
from ....runtime import RuntimePath
from ....utils.file import read_markdown, yaml
from ....utils.file.atomic import atomic_write_yaml
from .models import (
    ExecType,
    PendingInfo,
    Skill,
    SkillMetadata,
    SkillsManagerConfig,
)
from .sandbox import CodeValidator

INDEX_NAME = "index.yaml"
SKILL_DOC_NAME = "SKILL.md"

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_ALLOWED_PARAM_TYPES = {
    "string", "integer", "number", "boolean", "array", "object", "null", "any",
}
#: controller / ctl 共用的返回上限（第二道封顶，沙盒内还有 stdout 限流）。
DEFAULT_MAX_RESULT_CHARS = 64 * 1024


def _safe_skill_id(value: Any) -> str:
    """技能 id 会拼进路径，必须白名单校验，杜绝 ../ 逃逸。"""
    text = str(value or "").strip()
    if not _ID_RE.fullmatch(text):
        raise ValueError(
            f"非法 skill_id: {text!r}（只允许字母数字 _ -，长度 1-64）"
        )
    return text


def cap_skill_result(data: Any, max_chars: int = DEFAULT_MAX_RESULT_CHARS) -> Dict[str, Any]:
    """技能返回体封顶。只截字符串 / 大对象摘要，不改动 ok / error 语义。"""
    if not isinstance(data, dict):
        return {
            "ok": False,
            "error": "技能返回结构非法",
            "truncated": False
        }
    out: Dict[str, Any] = dict(data)
    truncated = bool(out.get("truncated"))
    limit = max(256, int(max_chars))
    for key in ("stdout", "error"):
        value = out.get(key)
        if isinstance(value, str) and len(value) > limit:
            out[key] = value[:limit] + "..."
            truncated = True
    payload = out.get("data")
    if isinstance(payload, str) and len(payload) > limit:
        out["data"] = payload[:limit] + "..."
        truncated = True
    elif payload is not None:
        try:
            size = len(json.dumps(payload, ensure_ascii=False, default=str))
        except Exception:  # noqa: BLE001
            size = len(repr(payload))
        if size > limit:
            out["data"] = {
                "_truncated": True,
                "_type": type(payload).__name__,
                "_bytes": size,
            }
            truncated = True
    out["truncated"] = truncated
    return out


class ExternalSkillManager:
    """外部技能管理器（线程安全单例）。"""

    _instance: Optional["ExternalSkillManager"] = None
    _cls_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
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
        self._pending: Dict[str, PendingInfo] = {}
        self._observer = None

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
        """恢复元数据与状态；代码不进索引，按 entry 惰性补载。"""
        try:
            index = yaml.read_yaml(self._index_path)
        except Exception as exc:  # noqa: BLE001 - 首次启动属正常
            logger.debug(f"[Skills] 读取索引失败（首次启动属正常）: {exc}")
            return
        if not isinstance(index, dict):
            logger.warning(f"[Skills] 索引格式不是对象: {self._index_path}")
            return

        loaded = 0
        with self._lock:
            for skill_id, meta in index.items():
                try:
                    sid = _safe_skill_id(skill_id)
                except ValueError:
                    logger.warning(f"[Skills] 跳过非法技能 id: {skill_id!r}")
                    continue
                if not isinstance(meta, dict):
                    logger.warning(f"[Skills] 跳过格式错误的索引项: {sid}")
                    continue
                try:
                    skill = Skill.from_dict(meta)
                    skill.metadata.name = skill.metadata.name or sid
                    # pending 与 active 是正交状态：待审批的不允许执行。
                    if skill.pending:
                        skill.active = False
                        self._pending[sid] = PendingInfo.from_dict(
                            meta.get("pending_info")
                        )
                    else:
                        self._pending.pop(sid, None)
                    self._skills[sid] = skill
                    loaded += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"[Skills] 跳过损坏的技能 {sid}: {exc}")
        if loaded:
            logger.info(f"[Skills] 已加载 {loaded} 个技能索引")

    def update_index(self) -> None:
        """原子写索引。任何状态变更都必须经过这里，否则重启即丢。"""
        with self._lock:
            payload: Dict[str, Any] = {}
            for skill_id, skill in self._skills.items():
                item = skill.to_dict()
                info = self._pending.get(skill_id)
                if info is not None:
                    item["pending_info"] = info.to_dict()
                payload[skill_id] = item
        try:
            os.makedirs(Path(self._config.skill_dir), exist_ok=True)
            atomic_write_yaml(str(self._index_path), payload)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[Skills] 写入索引失败 {self._index_path}: {exc}")

    # ---------- 目录监听 ----------

    def watch_directory(self) -> None:
        """启动目录监听。watchdog 不可用时静默降级（不拖垮启动）。"""
        try:
            from watchdog.events import FileSystemEventHandler  # type: ignore
            from watchdog.observers import Observer  # type: ignore
        except Exception:  # noqa: BLE001
            logger.debug("[Skills] watchdog 未安装，跳过目录监听")
            return

        manager = self

        class _Handler(FileSystemEventHandler):
            def on_created(self, event) -> None:
                path = Path(str(event.src_path))
                if path.is_dir():
                    if (path / SKILL_DOC_NAME).is_file():
                        manager._discover(path.name)
                    return
                if path.name == SKILL_DOC_NAME:
                    manager._discover(path.parent.name)
                elif path.name == INDEX_NAME:
                    manager.load_index()

            def on_modified(self, event) -> None:
                path = Path(str(event.src_path))
                if path.name == INDEX_NAME:
                    manager.load_index()
                elif path.name == SKILL_DOC_NAME:
                    # 文档变了：让代码缓存失效并重新登记
                    manager._discover(path.parent.name)

            def on_deleted(self, event) -> None:
                path = Path(str(event.src_path))
                if path.name == SKILL_DOC_NAME:
                    manager._remove_skill(path.parent.name)
                elif path.name == INDEX_NAME:
                    manager.load_index()

        try:
            root = Path(self._config.skill_dir)
            root.mkdir(parents=True, exist_ok=True)
            observer = Observer()
            observer.schedule(_Handler(), str(root), recursive=True)
            observer.daemon = True
            observer.start()
            self._observer = observer
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[Skills] 启动目录监听失败: {exc}")

    def _discover(self, skill_id: Any) -> None:
        try:
            sid = _safe_skill_id(skill_id)
        except ValueError:
            return
        if self._load_single_file(sid):
            self.update_index()

    def _remove_skill(self, skill_id: Any) -> None:
        try:
            sid = _safe_skill_id(skill_id)
        except ValueError:
            return
        with self._lock:
            existed = sid in self._skills
            self._skills.pop(sid, None)
            self._pending.pop(sid, None)
        if existed:
            self.update_index()
            logger.info(f"[Skills] 已移除磁盘上消失的技能 {sid}")

    # ---------- 文档解析 / 脚本探测 ----------

    def _read_doc(
        self,
        doc_path: Path,
        skill_id: str
    ) -> Optional[Tuple[SkillMetadata, str, Dict[str, Any]]]:
        """解析 SKILL.md 的 frontmatter + 正文 + params_schema。"""
        try:
            content = read_markdown(doc_path, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[Skills] 读取技能失败 {doc_path}: {exc}")
            return None
        if not str(content or "").startswith("---"):
            logger.warning(f"[Skills] {doc_path} 缺少 frontmatter，已跳过")
            return None
        parts = str(content).split("---", 2)
        if len(parts) < 3:
            return None
        try:
            raw = yaml.parse_yaml(parts[1]) or {}
            if not isinstance(raw, dict) or not raw:
                raise ValueError("frontmatter 不是有效的 YAML 对象")
            metadata = SkillMetadata(
                name=str(raw.get("name") or skill_id).strip(),
                description=str(raw.get("description", "") or "").strip(),
                license=str(raw.get("license", "MIT") or ""),
                version=str(raw.get("version", "1.0.0") or ""),
                author=str(raw.get("author", "") or ""),
            )
            schema = raw.get("params_schema")
            params_schema = dict(schema) if isinstance(schema, dict) else {}
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[Skills] 元数据解析失败 {doc_path}: {exc}")
            return None
        ok, errors = metadata.validate()
        if not ok:
            logger.warning(f"[Skills] 技能 {skill_id} 校验失败: {'; '.join(errors)}")
            return None
        return metadata, parts[2].strip(), params_schema

    @staticmethod
    def _probe_scripts(skill_dir: Path, *, load_code: bool = False):
        """探测脚本：返回 (exec_type, entry, code)。

        优先级 python > javascript > shell，与"shell 明确拒绝执行"一致：
        即使只有 .sh 也标记为 SHELL，不会默默当 NONE 跳过。
        `load_code=False` 用于目录扫描，避免把大段源码读进内存。
        """
        scripts_dir = skill_dir / "scripts"
        if not scripts_dir.is_dir():
            return ExecType.NONE, "", ""
        priority = (
            (".py", ExecType.PYTHON),
            (".js", ExecType.JAVASCRIPT),
            (".sh", ExecType.SHELL),
        )
        try:
            entries = sorted(scripts_dir.iterdir())
        except OSError as exc:  # noqa: BLE001 - 单个目录不可读不该中断整次扫描
            logger.warning(f"[Skills] 脚本目录不可读 {scripts_dir}: {exc}")
            return ExecType.NONE, "", ""
        for suffix, exec_type in priority:
            for file in entries:
                if file.suffix.lower() != suffix or not file.is_file():
                    continue
                code = ""
                if load_code and exec_type == ExecType.PYTHON:
                    try:
                        code = file.read_text(encoding="utf-8")
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(f"[Skills] 读取脚本失败 {file}: {exc}")
                return exec_type, file.name, code
        return ExecType.NONE, "", ""

    def _fill_code_unlocked(self, skill_id: str, skill: Skill) -> bool:
        """惰性补载 code / context / entry / params_schema。调用方持有 `_lock`。

        这是"重启后技能可执行"的关键：索引里没有代码，第一次执行或
        激活时按 entry 从磁盘读回来。
        """
        if skill.code_loaded:
            return True
        skill_dir = Path(self._config.skill_dir) / _safe_skill_id(skill_id)
        parsed = self._read_doc(skill_dir / SKILL_DOC_NAME, skill_id)
        if parsed is None:
            return False
        metadata, body, schema = parsed
        exec_type, entry, code = self._probe_scripts(skill_dir, load_code=True)
        skill.metadata = metadata
        skill.context = body
        skill.params_schema = schema
        skill.exec_type = exec_type
        skill.entry = entry
        skill.code = code if exec_type == ExecType.PYTHON else ""
        skill.code_loaded = True
        return exec_type != ExecType.PYTHON or bool(code)

    # ---------- 单个技能登记 ----------

    def _load_single_file(self, skill_id: str) -> bool:
        """登记一个技能。目录扫描 / 安装 / watchdog 共用同一入口。"""
        sid = _safe_skill_id(skill_id)
        skill_dir = Path(self._config.skill_dir) / sid
        parsed = self._read_doc(skill_dir / SKILL_DOC_NAME, sid)
        if parsed is None:
            return False
        metadata, _body, schema = parsed
        exec_type, entry, _code = self._probe_scripts(skill_dir)

        with self._lock:
            existing = self._skills.get(sid)
            skill = Skill(
                metadata=metadata,
                exec_type=exec_type,
                active=bool(existing.active) if existing is not None else False,
                entry=entry,
                params_schema=schema,
            )
            if existing is None:
                skill.pending = True
                skill.active = False
                self._pending[sid] = PendingInfo(
                    reason="new_skill",
                    source="filesystem",
                    discovered_at=time.time(),
                )
            else:
                skill.pending = sid in self._pending
            self._skills[sid] = skill
        logger.info(f"[Skills] 已登记技能 {sid} (type={exec_type.value})")
        return True

    # ---------- 扫描 / 安装 / 卸载 / 校验 ----------

    def rescan(self) -> Dict[str, Any]:
        """完整目录扫描 + 索引重建。新增 SKILL.md 能被发现。"""
        root = Path(self._config.skill_dir)
        found: List[str] = []
        if root.is_dir():
            for child in sorted(root.iterdir()):
                if not child.is_dir() or not (child / SKILL_DOC_NAME).is_file():
                    continue
                try:
                    sid = _safe_skill_id(child.name)
                except ValueError:
                    continue
                if self._load_single_file(sid):
                    found.append(sid)
        with self._lock:
            stale = [sid for sid in self._skills if sid not in found]
            for sid in stale:
                self._skills.pop(sid, None)
                self._pending.pop(sid, None)
            total = len(self._skills)
            pending = sorted(self._pending)
        self.update_index()
        return {
            "ok": True,
            "total": total,
            "found": found,
            "removed": stale,
            "pending": pending,
        }

    def reload(self) -> Dict[str, Any]:
        """`/skill/reload` 与 `/skill/rescan` 共用真扫描实现。"""
        return self.rescan()

    def install_skill(self, skill_id: str) -> Dict[str, Any]:
        """登记安装：把目录里已有的 SKILL.md 纳入索引，状态为待审批。"""
        try:
            sid = _safe_skill_id(skill_id)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        doc = Path(self._config.skill_dir) / sid / SKILL_DOC_NAME
        if not doc.is_file():
            return {"ok": False, "error": f"技能目录缺少 {SKILL_DOC_NAME}: {sid}"}
        if not self._load_single_file(sid):
            return {"ok": False, "error": f"技能 {sid} 元数据或脚本校验失败"}
        self.update_index()
        with self._lock:
            skill = self._skills.get(sid)
        return {
            "ok": True,
            "skill_id": sid,
            "pending": bool(skill and skill.pending),
            "active": bool(skill and skill.active),
            "exec_type": (
                skill.exec_type.value if skill is not None else ExecType.NONE.value
            ),
            "entry": str(skill.entry or "") if skill is not None else "",
        }

    def uninstall_skill(
        self, skill_id: str, *, remove_files: bool = False
    ) -> Dict[str, Any]:
        """卸载登记；默认**不删用户文件**，避免误删。"""
        try:
            sid = _safe_skill_id(skill_id)
        except ValueError as exc:
            return {
                "ok": False,
                "error": str(exc)
            }
        with self._lock:
            existed = sid in self._skills
            self._skills.pop(sid, None)
            self._pending.pop(sid, None)
        self.update_index()
        removed_files = False
        if remove_files and existed:
            target = Path(self._config.skill_dir) / sid
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
                removed_files = not target.exists()
        return {
            "ok": existed,
            "skill_id": sid,
            "removed_files": removed_files,
            "error": "" if existed else f"未知 skill: {sid}",
        }

    def validate_skill(self, skill_id: str) -> Dict[str, Any]:
        """校验入口：元数据 / 参数 schema / 代码 AST 白名单。只读不改状态。

        shell 类型仍可通过校验（"可识别、可见、可启用"），但会带 warning
        明确标注执行会被拒绝，不误报为校验失败。
        """
        try:
            sid = _safe_skill_id(skill_id)
        except ValueError as exc:
            return {"ok": False, "skill_id": "", "errors": [str(exc)]}

        with self._lock:
            skill = self._skills.get(sid)
            if skill is None:
                return {
                    "ok": False, "skill_id": sid,
                    "errors": [f"未知 skill: {sid}"],
                }
            errors: List[str] = []
            warnings: List[str] = []
            ok_meta, meta_errors = skill.metadata.validate()
            errors.extend(meta_errors)
            code_ok = self._fill_code_unlocked(sid, skill)

        if not code_ok:
            errors.append("SKILL.md 或 scripts/ 不可读，代码无法补载")

        schema = skill.params_schema or {}
        if schema:
            if not isinstance(schema, dict):
                errors.append("params_schema 必须是对象")
            else:
                props = schema.get("properties")
                required = schema.get("required")
                if props is not None and not isinstance(props, dict):
                    errors.append("params_schema.properties 必须是对象")
                if required is not None and not isinstance(required, (list, tuple)):
                    errors.append("params_schema.required 必须是列表")
                for key, spec in (props or {}).items():
                    if not isinstance(spec, dict) or "type" not in spec:
                        errors.append(f"params_schema.properties.{key} 缺少 type")
                    elif str(spec.get("type") or "").lower() not in _ALLOWED_PARAM_TYPES:
                        errors.append(
                            f"params_schema.properties.{key}.type 不支持: {spec.get('type')}"
                        )

        if skill.exec_type == ExecType.PYTHON:
            if not skill.code:
                errors.append("没有可执行的 python 脚本")
            else:
                try:
                    CodeValidator().validate(skill.code)
                except ValueError as exc:
                    errors.append(f"代码未通过沙盒白名单: {exc}")
        elif skill.exec_type == ExecType.SHELL:
            warnings.append("shell 技能可识别，但执行时被明确拒绝")
        elif skill.exec_type == ExecType.JAVASCRIPT:
            warnings.append("javascript 技能尚未实现，执行时被明确拒绝")

        return {
            "ok": len(errors) == 0,
            "skill_id": sid,
            "errors": errors,
            "warnings": warnings,
            "exec_type": skill.exec_type.value,
            "active": bool(skill.active),
            "pending": bool(skill.pending),
            "entry": str(skill.entry or ""),
            "params_schema": dict(schema),
        }

    # ---------- 启用 / 停用 ----------

    def activate_skill(self, skill_id: str) -> bool:
        with self._lock:
            skill = self._skills.get(skill_id)
            if skill is None:
                return False
            if skill.exec_type == ExecType.PYTHON and not self._fill_code_unlocked(
                skill_id, skill
            ):
                logger.warning(f"[Skills] 技能 {skill_id} 代码补载失败，拒绝启用")
                return False
            skill.active = True
            skill.pending = False
            self._pending.pop(skill_id, None)
        self.update_index()
        return True

    def deactivate_skill(self, skill_id: str) -> bool:
        with self._lock:
            skill = self._skills.get(skill_id)
            if skill is None:
                return False
            skill.active = False
        self.update_index()
        return True

    def reject_skill(self, skill_id: str) -> bool:
        with self._lock:
            self._pending.pop(skill_id, None)
            removed = self._skills.pop(skill_id, None) is not None
        self.update_index()
        return removed

    # ---------- 查询 ----------

    def get_active_skills(self) -> Dict[str, Skill]:
        with self._lock:
            return {
                k: v for k, v in self._skills.items()
                if v.active and not v.pending
            }

    def get_pending_skills(self) -> Dict[str, str]:
        """保持既有 `Dict[str, str]` 形状，供 `SkillListData.pending` 使用。"""
        with self._lock:
            return {
                sid: self._skills[sid].description
                for sid in self._pending
                if sid in self._skills
            }

    def get_pending_detail(self) -> Dict[str, Dict[str, Any]]:
        """结构化 pending 元数据（PR-3 新增）。"""
        with self._lock:
            return {
                sid: info.to_dict() for sid,
                info in self._pending.items()
            }

    def get_skill(self, skill_id: str) -> Optional[Skill]:
        with self._lock:
            return self._skills.get(skill_id)

    def list_skills(self, active_only: bool = False) -> Dict[str, str]:
        with self._lock:
            items = self.get_active_skills() if active_only else dict(self._skills)
        return {sid: skill.description for sid, skill in items.items()}

    # ---------- 执行 ----------

    def _prepare_execution(
        self, skill_id: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行前的统一校验 + 上下文构造。async / sync 两个入口共用。"""
        params = dict(params or {})
        with self._lock:
            skill = self._skills.get(skill_id)
            if skill is None:
                return {"ok": False, "error": f"未知 skill: {skill_id}"}
            if skill.pending:
                return {"ok": False, "error": f"技能待审批，请先激活: {skill_id}"}
            if not skill.active:
                return {"ok": False, "error": f"skill 未启用: {skill_id}"}
            if skill.exec_type == ExecType.SHELL:
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
            if not self._fill_code_unlocked(skill_id, skill):
                return {"ok": False, "error": f"skill {skill_id} 代码补载失败"}
            if not skill.code:
                return {
                    "ok": False,
                    "error": f"skill {skill_id} 代码为空"
                }
            ok_params, param_errors = skill.validate_params(params or {})
            if not ok_params:
                return {
                    "ok": False,
                    "error": "参数校验失败: " + "; ".join(param_errors),
                }
            code = skill.code

        # 技能产出限制在 <workspace>/skill/<skill_id>/。
        # 沙盒 AST 白名单禁用 open / os / pathlib / subprocess，
        # 注入的 write_output 是技能落盘的唯一通道。
        try:
            from ....security import make_output_writer, service_output_dir

            output_dir = service_output_dir("skill", skill_id)
            write_output = make_output_writer("skill", skill_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[Skills] 工作区输出目录不可用: {exc}")
            output_dir = ""
            write_output = None

        context: Dict[str, Any] = {
            "input_data": params,
            "params": params,
            "result": None,
            "output_dir": output_dir,
        }
        if write_output is not None:
            context["write_output"] = write_output
        return {"ok": True, "code": code, "context": context}

    async def execute_skill(
        self, skill_id: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """异步入口（ctl.py 命令链使用）。"""
        prep = self._prepare_execution(skill_id, params)
        if not prep.get("ok"):
            return {"ok": False, "error": str(prep.get("error") or "执行失败")}
        try:
            return await self._executor.execute(prep["code"], context=prep["context"])
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[Skills] 执行 {skill_id} 失败: {exc}")
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def execute_skill_sync(
        self, 
        skill_id: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """同步入口（controller 用 `to_thread` 调用）"""
        prep = self._prepare_execution(skill_id, params)
        if not prep.get("ok"):
            return {"ok": False, "error": str(prep.get("error") or "执行失败")}
        try:
            return self._executor.execute_sync(prep["code"], context=prep["context"])
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[Skills] 同步执行 {skill_id} 失败: {exc}")
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    # ---------- 关闭 ----------

    def close(self) -> None:
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=2)
            except Exception:  # noqa: BLE001
                pass
            self._observer = None
        self.update_index()
        with self._lock:
            self._skills.clear()
            self._pending.clear()
        self._initialized = False
