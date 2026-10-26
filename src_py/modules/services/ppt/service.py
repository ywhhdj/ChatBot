"""PPT 对外服务：模板 + 大纲 + 渲染 三合一。

修复对应清单：K23 / K25 / K26

注册为 ServiceManager 的一个服务（`ServiceId.PPT`），
`get_tools()` 返回 `ToolFunction`，可直接进命令文档。

长耗时（Kimi 网络调用）全部提交到任务调度器，返回 task_id，
前端按需取回 —— 不在 UI 线程 / Web loop 上 await 网络 IO。
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from ...pipeline.enum import AdapterType
from ...events import on_event_class, types
from ...logger import logger
from ...manager.service.decorator import Service
from ...pipeline.models import ToolFunction, ToolFunctionParameters
from .. import ServiceId
from ..base import BaseService, ServiceState
from .models import DeckSpec, RenderResult, TemplateSpec
from .renderer import PptRenderService
from .template import get_template_service

# 任务表：task_id -> {...}
_JOBS: Dict[str, Dict[str, Any]] = {}
_JOB_LOCK = threading.RLock()

def get_llm() -> Any:
    from ...manager.pipeline import pipeline_manager
    return pipeline_manager.__get_adapter_manager(AdapterType.LLM)


@on_event_class([
    (types.PptEventType.PPT_STOP, "stop"),
])
@Service(id=ServiceId.PPT)
class PptService(BaseService):
    """PPT 生成服务。

    三段式：模板 → 大纲 → 渲染。
    """

    name = "PPT生成"
    description = "基于 LLM 的模板化演示文稿生成服务"

    def __init__(
        self,
        api_key: str = "",
        model: str = "",
        base_url: str = "",
        default_template: str = "consulting",
        default_pages: int = 10,
        output_dir: str = "",
    ) -> None:
        super().__init__()
        self.api_key = api_key or os.environ.get("MOONSHOT_API_KEY", "")
        self.model = model or ""
        self.base_url = base_url or ""
        self.default_template = default_template or "consulting"
        self.default_pages = int(default_pages or 10)
        self.output_dir = output_dir

        self.templates = get_template_service()
        self.renderer = PptRenderService(output_dir=output_dir or None)
        self.running = True
        self.set_status()

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
        """调 Kimi 生成结构化大纲。"""
        from .prompts import build_outline_system, build_outline_user

        tpl = self.resolve_template(template_id, style)
        llm = get_llm()
        if not llm.is_init:
            raise RuntimeError("LLM 未配置：缺少 MOONSHOT_API_KEY")

        system = build_outline_system(tpl)
        user = build_outline_user(
            topic=topic,
            pages=int(pages or self.default_pages),
            audience=audience,
            scenario=scenario,
            style=style,
            material=material,
        )
        data = llm.complete_json(system, user)
        deck = DeckSpec.from_dict(data)
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
        file_name: Optional[str] = None,
    ) -> RenderResult:
        """一步到位：大纲 + 渲染。"""
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
        with _JOB_LOCK:
            _JOBS[task_id] = {
                "state": "pending", 
                "result": None,
                "error": None, 
                "created_at": time.time()
            }

        def _job() -> RenderResult:
            return self.generate(**kwargs)

        ref = runtime.manager.task_manager.submit(_job, timeout=600.0, task_type="sync")  # type: ignore[union-attr]
        with _JOB_LOCK:
            _JOBS[task_id]["ref"] = ref
            _JOBS[task_id]["state"] = "running"
        return task_id

    def job_status(self, task_id: str) -> Dict[str, Any]:
        with _JOB_LOCK:
            job = _JOBS.get(str(task_id))
        if job is None:
            return {
                "task_id": task_id,
                "state": "not_found"
            }
        ref = job.get("ref")
        result = None
        state = job.get("state")
        if ref is not None:
            try:
                done = ref.is_done() if hasattr(ref, "is_done") else None
                if done:
                    state = "done"
                    try:
                        result = ref.result()
                    except Exception as e:  # noqa: BLE001
                        state = "failed"
                        job["error"] = str(e)
            except Exception:  # noqa: BLE001
                pass
        out = {"task_id": task_id, "state": state}
        if result is not None:
            out["result"] = result.to_dict() if hasattr(result, "to_dict") else result
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
