"""PPT 对外服务：模板 + 大纲 + 渲染 三合一"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from collections import OrderedDict
from typing import Any, Dict, List, Optional

from ...core.pipeline.models import ToolFunction, ToolFunctionParameters
from ...events import on_event_class, types
from ...logger import logger
from ... import keys
from ...providers.entity import LLM
from .._async import run_coroutine
from ..base import BaseService, ServiceState
from ..manager import Service
from .models import DeckSpec, RenderResult, TemplateSpec
from .prompts import (
    OFFICIAL_CONVENTIONS,
    build_outline_system,
    build_outline_user,
)
from .renderer import PptRenderService
from .template import get_template_service

# 有界任务表：task_id -> {...}。旧实现无上限、无 TTL，长时间运行会持续堆积
# 已完成的 RenderResult 与 TaskReference。
_JOBS: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
_JOB_LOCK = threading.RLock()
_JOB_LIMIT = 64
_JOB_TTL = 3600.0

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def _parse_deck_json(raw: str) -> Dict[str, Any]:
    """LLM 返回可能被 ```json 包裹或夹前后说明；只接受含 slides 的对象。"""
    text = str(raw or "").strip()
    candidates = [text]
    block = _JSON_BLOCK.search(text)
    if block:
        candidates.append(block.group(1).strip())
    obj = _JSON_OBJECT.search(text)
    if obj:
        candidates.append(obj.group(0))
    for candidate in candidates:
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict) and data.get("slides"):
            return data
    raise RuntimeError("LLM 未返回合法的大纲 JSON")


def _prune_jobs(now: float) -> None:
    """调用方持有 _JOB_LOCK。"""
    for task_id, job in list(_JOBS.items()):
        if now - float(job.get("created_at", 0)) > _JOB_TTL:
            _JOBS.pop(task_id, None)
    while len(_JOBS) > _JOB_LIMIT:
        _JOBS.popitem(last=False)

@on_event_class([
    (types.PptEventType.PPT_STOP, "stop"),
])
@Service(id=keys.ServiceKeys.PPT)
class PptService(BaseService):
    """PPT 生成服务。

    三段式：模板 → 大纲 → 渲染。
    """

    name = "PPT生成"
    description = "基于 LLM 的模板化演示文稿生成服务"

    def __init__(
        self,
        default_template: str = "consulting",
        default_pages: int = 10,
    ) -> None:
        super().__init__()
        self.default_template = default_template or "consulting"
        self.default_pages = int(default_pages or 10)
        try:
            from ...security import service_output_dir

            self.output_dir = service_output_dir("ppt")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[PPT] 工作区产出目录暂不可用: {exc}")
            self.output_dir = ""

        self.templates = get_template_service()
        self.renderer = PptRenderService()
        # 构造尚未启动：状态由 ServiceManager.start_service 置为 RUNNING。
        # 旧实现构造即 running，管理器再启动会被"已在运行"直接拒绝。
        self.running = False
        self.set_status()
        self.context_profile = {
            "dedicated_stage": True,
            # 只带"沟通策略 + 产出物约定"，不带设计师人设 ——
            # 人设属于服务内部的大纲生成阶段，由 prompts.build_outline_system 提供
            "system_prompt": "\n".join([
                "## PPT 服务作业约定",
                OFFICIAL_CONVENTIONS.strip(),
            ]),
            "keep_character": False,
            "keep_history": False,
            "directives": [
                "回复只讲产出了什么、放在哪里，用相对路径列出文件。",
                "不要汇报中间用了哪些命令和库，不要输出 JSON 或代码。",
            ],
            "budget": {
                # 大纲/渲染阶段的正文更长，常规 3000 会截断
                "total_tokens": 8000,
                "reserve_for_input": 1024,
            },
        }

    def on_config_change(self, old_config: Dict, new_config: Dict) -> None:
        template = str(new_config.get("default_template") or "").strip()
        if template:
            self.default_template = template
        pages = new_config.get("default_pages")
        if pages:
            try:
                self.default_pages = max(1, min(int(pages), 60))
            except (TypeError, ValueError):
                pass

    # ---------- 状态 ----------

    def set_status(self) -> None:
        super().set_status(ServiceState.RUNNING if self.running else ServiceState.STOPPED)

    # ---------- 能力 ----------

    def list_templates(self) -> List[Dict[str, Any]]:
        return self.templates.list_templates()

    def resolve_template(
        self,
        template_id: Optional[str] = None,
        style: str = "",
        colors: Optional[Dict[str, str]] = None,
    ) -> TemplateSpec:
        return self.templates.resolve(template_id, style, colors)

    def outline(
        self,
        topic: str,
        pages: Optional[int] = None,
        audience: str = "",
        scenario: str = "",
        style: str = "",
        material: str = "",
        template_id: Optional[str] = None,
    ) -> DeckSpec:
        """用已初始化的 LLM 门面生成结构化大纲。

        旧实现 `events.emit(events.types.ProviderEventType.LLM_GENERATE)` 有三重问题：
        emit 需要 BaseEvent 却传了字符串（必抛 AttributeError）、该事件没有任何
        监听者、且完全没有把 system/user 提示词发出去 —— 大纲链路从未可用。
        """
        tpl = self.resolve_template(template_id, style)
        system = build_outline_system(tpl)
        user = build_outline_user(
            topic=topic,
            pages=int(pages or self.default_pages),
            audience=audience,
            scenario=scenario,
            style=style,
            material=material,
        )
        llm = LLM()
        if not llm.is_initialized:
            raise RuntimeError("LLM 未初始化，无法生成 PPT 大纲")
        raw = run_coroutine(llm.process_message(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            max_tokens=2048,
        ))
        deck = DeckSpec.from_dict(_parse_deck_json(raw))
        if not deck.slides:
            raise RuntimeError("LLM 未返回任何页面")
        # 兜底：补封面 / 结尾
        self._ensure_edges(deck, topic)
        return deck

    def render(
        self,
        deck: DeckSpec,
        template_id: Optional[str] = None,
        style: str = "",
        colors: Optional[Dict[str, str]] = None,
        file_name: Optional[str] = None,
    ) -> RenderResult:
        tpl = self.resolve_template(template_id, style, colors)
        logger.info(f"PPT 渲染：{len(deck.slides)} 页，模板 {tpl.name}，输出目录 {self.output_dir}")
        return self.renderer.render(deck, tpl, file_name)

    def generate(
        self,
        topic: str,
        pages: Optional[int] = None,
        template_id: Optional[str] = None,
        style: str = "",
        material: str = "",
        audience: str = "",
        scenario: str = "",
        file_name: Optional[str] = None
    ) -> RenderResult:
        """一步到位：大纲 + 渲染"""
        deck = self.outline(topic, pages, audience, scenario, style, material, template_id)
        return self.render(deck, template_id, style, file_name=file_name)

    @staticmethod
    def _ensure_edges(deck: DeckSpec, topic: str) -> None:
        if not deck.slides:
            return
        if deck.slides[0].layout != "cover":
            deck.slides.insert(0, type(deck.slides[0])(
                layout="cover", 
                title=deck.title or topic,
                subtitle=deck.subtitle
            ))
        if deck.slides[-1].layout != "closing":
            deck.slides.append(type(deck.slides[0])(
                layout="closing",
                title="感谢观看",
                subtitle=deck.title or topic
            ))

    # ---------- 异步任务（K26） ----------

    def submit_generate(self, **kwargs: Any) -> str:
        """提交生成任务到调度器，返回 task_id。"""
        from ... import runtime

        task_id = uuid.uuid4().hex[:16]
        now = time.time()
        with _JOB_LOCK:
            _prune_jobs(now)
            _JOBS[task_id] = {
                "state": "pending",
                "result": None,
                "error": None,
                "created_at": now,
            }

        def _job() -> RenderResult:
            return self.generate(**kwargs)

        try:
            ref = runtime.manager.task_manager.submit(  # type: ignore[union-attr]
                _job, timeout=600.0, task_type="sync"
            )
        except Exception as exc:  # noqa: BLE001
            with _JOB_LOCK:
                job = _JOBS.get(task_id)
                if job is not None:
                    job["state"] = "failed"
                    job["error"] = str(exc)
            raise
        with _JOB_LOCK:
            job = _JOBS.get(task_id)
            if job is not None:
                job["ref"] = ref
                job["state"] = "running"
        return task_id

    def job_status(self, task_id: str) -> Dict[str, Any]:
        with _JOB_LOCK:
            _prune_jobs(time.time())
            job = _JOBS.get(str(task_id))
            if job is None:
                return {"task_id": task_id, "state": "not_found"}
            # 终态直接读缓存，不再每次都去取 TaskReference 的结果
            if job.get("state") not in ("done", "failed"):
                ref = job.get("ref")
                if ref is not None:
                    try:
                        if ref.is_done():
                            try:
                                value = ref.result()
                            except Exception as exc:  # noqa: BLE001
                                job["state"] = "failed"
                                job["error"] = str(exc)
                            else:
                                job["state"] = "done"
                                job["result"] = (
                                    value.to_dict() if hasattr(value, "to_dict") else value
                                )
                    except Exception:  # noqa: BLE001
                        pass
            out: Dict[str, Any] = {"task_id": task_id, "state": job.get("state")}
            if job.get("result") is not None:
                out["result"] = job["result"]
            if job.get("error"):
                out["error"] = job["error"]
            return out

    # ---------- 生命周期 ----------

    def start(self, *args: Any, **kwargs: Any) -> Any:
        self.running = True
        self.set_status()
        return True

    def stop(self, *args: Any, **kwargs: Any) -> Any:
        self.running = False
        self.set_status()
        return True

    def close(self, *args: Any, **kwargs: Any) -> Any:
        return self.stop()

    # ---------- 工具声明 ----------

    def get_tools(self) -> List[ToolFunction]:
        return [
            ToolFunction(
                name="generate",
                description="根据主题一键生成 PPT（选模板、出大纲、渲染为可编辑 pptx）",
                parameters=ToolFunctionParameters(
                    type="object",
                    properties={
                        "topic": {"type": "string", "description": "演示主题或一句话需求"},
                        "pages": {"type": "integer", "description": "内容页数量，默认 10"},
                        "template_id": {
                            "type": "string",
                            "description": "模板 id：consulting/marketing/academic/launch/funding",
                        },
                        "style": {
                            "type": "string",
                            "description": "额外风格要求，如配色、受众",
                        },
                        "material": {
                            "type": "string",
                            "description": "原始材料，有则优先依据",
                        },
                    },
                    required=["topic"],
                ),
            ),
            ToolFunction(
                name="outline",
                description="只生成演示大纲，不渲染文件",
                parameters=ToolFunctionParameters(
                    type="object",
                    properties={
                        "topic": {"type": "string", "description": "演示主题"},
                        "pages": {"type": "integer", "description": "内容页数量"},
                        "template_id": {"type": "string", "description": "模板 id"},
                    },
                    required=["topic"],
                ),
            ),
            ToolFunction(
                name="templates",
                description="列出可用的 PPT 模板",
            ),
        ]
