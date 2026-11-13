"""角色编排器：在"纯角色聊天"与"后台任务执行"之间分流。
"""
from __future__ import annotations
import asyncio
import inspect
import json
import re
import threading
from collections import OrderedDict
from dataclasses import replace
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, List, Optional

from ... import runtime
from ...models import Role
from ...providers.entity import LLM
from ..routes.intent import IntentRouter
from ..routes.models import RouteType
from ..tools.ctl import CLTTool
from ..context.prompt import PromptBuilder
from ..context.assembly import (
    NO_TOOLS,
    AssemblyPlan,
    ServiceContextProfile,
    StageKind,
    ToolBudgetState,
    next_stage,
    plan_for,
    profile_of,
)
from ...characters.models import Character
from .models import OrchestrationResult
from ...logger import logger
from ...logger import audit
from ..native.task_state import StopReason, TaskRecord, finish
from ..context.request import RequestContext, set_current, reset_current

LLMCaller = Callable[[List[Dict[str, str]]], Awaitable[str]]
CommandExecutor = Callable[[str], Awaitable[Any]]
from ...types.common import Message


async def _resolve(value: Any) -> Any:
    """同时兼容 TaskReference / 协程 / 普通值 / 含 results 的字典。"""
    if value is None:
        return None
    if hasattr(value, "wait_async") and callable(value.wait_async):
        return await value.wait_async()  # type: ignore[union-attr]
    if hasattr(value, "__await__"):
        return await value
    return value


class CharacterOrchestrator:
    """把用户输入分流到纯角色聊天或后台任务代理。"""

    def __init__(self, llm_manager: LLM) -> None:
        from ... import runtime

        self._char_mgr = runtime.manager.character_manager
        self._llm = llm_manager
        self._router = IntentRouter()
        from ..context.user import UserContext

        self._user_context = UserContext()
        self._last_result = OrchestrationResult()
        self._service_orch = CLTTool()
        #: 本轮实际执行的命令条数（摘要与审计用）
        self._last_commands: List[Any] = []
        #: 轻量路由判断缓存：同一句话不重复付费调用 LLM。
        #: 有界 LRU，避免长期运行后无上限增长（旧实现到 256 条整表清空，
        #: 会周期性把热点全部打回付费调用）。
        self._judge_cache: "OrderedDict[str, str]" = OrderedDict()
        self._judge_cache_limit = 256
        self._judge_cache_lock = threading.RLock()

    @staticmethod
    def _usage_snapshot(llm: LLM) -> Dict[str, int]:
        getter = getattr(llm, "get_usage_snapshot", None)
        if callable(getter):
            try:
                return dict(getter()) #type: ignore[arg-type]
            except Exception:  # noqa: BLE001
                return {}
        return {}

    @staticmethod
    def _usage_delta(before: Dict[str, int], after: Dict[str, int]) -> Dict[str, int]:
        return {
            key: max(0, int(after.get(key, 0)) - int(before.get(key, 0)))
            for key in ("prompt_tokens", "completion_tokens", "total_tokens", "calls")
        }

    # ---------- 非流式 ----------

    async def process(
        self,
        user_input: str,
        force_channel: Optional[RouteType] = None,
        session_id: str = "default",
        source: str = "text",
    ) -> OrchestrationResult:
        """非流式处理一轮输入。

        "多轮"真正的触发条件应该是"上一步产生了待执行的工具调用"，
        且必须累积 result。当前 `_handle_task` 内部已经是
        「生成命令 → 执行 → 带结果再总结」两阶段，单轮即可覆盖；
        因此这里回到**单轮执行**，并把可配置的轮次留给真正需要多步的场景。
        """
        from ...config import get_config

        config = get_config()
        timeout = getattr(config.llm, "timeout", None) or None
        ctx = RequestContext.create(session_id=session_id, source=source, timeout=timeout)

        token = set_current(ctx)
        usage_before = self._usage_snapshot(self._llm)
        try:
            result = OrchestrationResult()
            character = self._char_mgr.get_current()
            result.character_id = character.id if character else ""
            await self._user_context.add_user_message(
                user_input, session_id=ctx.session_id, source=source
            )
            channel = force_channel or (await self._router.route(
                user_input,
                llm_predict_func=self.__lightweight_route_judge,
            )).route_type
            result.route = channel

            if channel in (RouteType.TOOL_CALL, RouteType.MIXED):
                await self._handle_task(user_input, character, result, session_id=ctx.session_id)
            else:
                await self.__handle_chat(user_input, character, result, session_id=ctx.session_id)

            await self.__record_character_state(character, user_input, result)
            result.mood_after = character.state.mood if character else 4
            result.usage = self._usage_delta(
                usage_before, self._usage_snapshot(self._llm)
            )
            self._last_result = result
            return result
        finally:
            reset_current(token)

    # ---------- 流式 ----------

    async def process_stream(
        self,
        user_input: str,
        force_channel: Optional[RouteType] = None,
        session_id: str = "default",
        source: str = "text",
        result_holder: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[str, None]:
        from ...config import get_config

        config = get_config()
        timeout = getattr(config.llm, "timeout", None) or None
        ctx = RequestContext.create(session_id=session_id, source=source, timeout=timeout)

        token = set_current(ctx)
        #: 本轮请求的任务状态。**单一权威来源** ——
        #: 此前"这一轮进行到哪一步"散落在 tracer.phase / result 各字段里，
        #: 彼此可能不一致，且没有"终态不可再改"的约束。
        record = TaskRecord(
            task_id=ctx.request_id,
            request_id=ctx.request_id,
            session_id=ctx.session_id,
        )
        # 先建好结果对象并交给调用方：内层 finally 会无条件访问 result，
        # 旧实现把它放在 try 内，早期异常会被 NameError 覆盖成"未知错误"。
        result = OrchestrationResult()
        character = self._char_mgr.get_current()
        if result_holder is not None:
            result_holder["result"] = result
        usage_before = self._usage_snapshot(self._llm)
        try:
            await self._user_context.add_user_message(
                user_input, session_id=ctx.session_id, source=source
            )
            result.character_id = character.id if character else ""
            channel = force_channel or (await self._router.route(
                user_input,
                llm_predict_func=self.__lightweight_route_judge,
            )).route_type
            result.route = channel

            from ..tools.tracer import ToolCallTracer

            route_value = getattr(channel, "value", None) or str(channel or "")
            tracer = ToolCallTracer(
                emit_tools=ToolCallTracer.should_emit_tools(channel),
            )
            result.message_id = tracer.message_id
            tracer.start(route=route_value)
            listener = getattr(self._service_orch, "set_tool_listener", None)
            if callable(listener):
                listener(tracer.listener)

            try:
                if channel in (RouteType.TOOL_CALL, RouteType.MIXED):
                    tracer.phase_change("tooling")
                    async for chunk in self.__guarded(
                        self.__handle_task_stream(
                            user_input, character, result, session_id=ctx.session_id
                        ),
                        ctx, record,
                    ):
                        yield chunk
                else:
                    tracer.phase_change("answering")
                    async for chunk in self.__guarded(
                        self.__handle_chat_stream(
                            user_input, character, result, session_id=ctx.session_id
                        ),
                        ctx, record,
                    ):
                        yield chunk
                if not record.terminal:
                    record, _, _ = finish(record, StopReason.COMPLETED)
                tracer.phase_change("done")
            except Exception:
                tracer.phase_change("error")
                raise
            finally:
                result.tool_calls = list(tracer.tools)
                result.tools_skipped = sum(
                    1 for t in tracer.tools if t.get("status") == "skipped"
                )
                tracer.finish(
                    content=result.chat_response,
                    phase="error" if tracer.phase == "error" else "done"
                )
                if callable(listener):
                    try:
                        listener(None)
                    except Exception:  # noqa: BLE001
                        pass
                await self.__record_character_state(character, user_input, result)
                result.mood_after = character.state.mood if character else 4

                # 任务终态。异常路径也要收敛到明确终态，
                # 否则"失败但状态仍是 running"会让上层一直等。
                if not record.terminal:
                    reason = (
                        StopReason.CANCELLED if ctx.cancelled()
                        else StopReason.TIMED_OUT if ctx.expired()
                        else StopReason.ERROR
                    )
                    record, _, _ = finish(record, reason)
                result.stop_reason = record.reason
                result.usage = self._usage_delta(
                    usage_before, self._usage_snapshot(self._llm)
                )
                self.__emit_stream_audit(ctx, record)
        finally:
            reset_current(token)

    @staticmethod
    async def __guarded(
        source: AsyncGenerator[str, None],
        ctx: RequestContext,
        record: TaskRecord,
    ) -> AsyncGenerator[str, None]:
        """流式守卫：取消/超时后不再向下游投递 chunk。
        此前取消只作用于 LLM 客户端那一层，已经生成但还没发出的 chunk
        仍会继续 yield —— 前端看到"已取消"之后又冒出一段文字。
        """
        async for chunk in source:
            if ctx.cancelled():
                return
            if ctx.expired():
                return
            yield chunk

    def __emit_stream_audit(self, ctx: RequestContext, record: TaskRecord) -> None:
        """流式任务的终态审计。只记计数与原因码。"""
        try:
            audit.record(
                audit.Action.TASK_FINISH,
                request_id=ctx.request_id,
                session_id=ctx.session_id,
                decision=audit.Decision.ALLOW,
                result=(
                    audit.Result.SUCCESS if record.successful
                    else audit.Result.FAILURE
                ),
                reason_code=record.reason or StopReason.UNKNOWN.value,
                source=audit.Source.TASK,
                metadata={
                    "state": record.state.value,
                    "revision": record.revision,
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[Orchestrator] 审计事件失败: {type(exc).__name__}")

    # ---------- 聊天 ----------

    async def __handle_chat(
        self,
        user_input: str,
        character: Optional[Character],
        result: OrchestrationResult,
        session_id: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> None:
        built = self.__build_chat_prompt(character, user_input, session_id)
        messages = self.__to_messages(built, character, user_input, memory_limit=10)
        result.chat_response = (
            await self._llm.process_message(
                messages, temperature=temperature, max_tokens=max_tokens
            )
        ).strip()
        await self._user_context.add_assistant_message(result.chat_response, session_id=session_id)
        result.used_tokens_estimate = built.estimated_tokens

    async def __handle_chat_stream(
        self,
        user_input: str,
        character: Optional[Character],
        result: OrchestrationResult,
        session_id: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        built = self.__build_chat_prompt(character, user_input, session_id)
        messages = self.__to_messages(built, character, user_input, memory_limit=10)
        result.chat_response = ""
        async for chunk in self._llm.process_message_stream(
            messages,
            temperature=temperature,
            max_tokens=max_tokens
        ):
            if not chunk:
                continue
            chunk = chunk.strip()
            if not chunk:
                continue
            result.chat_response += chunk
            yield chunk
        await self._user_context.add_assistant_message(result.chat_response, session_id=session_id)
        result.used_tokens_estimate = built.estimated_tokens

    def __build_chat_prompt(
        self,
        character: Optional[Character],
        user_input: str,
        session_id: str = "default",
    ):
        """装配纯聊天 prompt"""
        memory_context = self.__collect_memory_context(session_id)
        return PromptBuilder.build(
            character=character,
            route=RouteType.PURE_CHAT,
            user_input=user_input,
            memory_context=memory_context,
            memory_limit=10,
            inject_randomness=True,
        )

    def __collect_memory_context(self, session_id: str) -> List[Dict[str, str]]:
        """记忆片段在前、近期对话在后，二者都限定在同一 session 内。"""
        ctx: List[Dict[str, str]] = []
        try:
            ctx.extend(self._user_context.get_memory_snippets(session_id=session_id))
        except Exception:  # noqa: BLE001
            pass
        ctx.extend(self._user_context.get_current_messages(session_id=session_id))
        return ctx

    # ---------- 任务 ----------

    async def __execute_commands(self, text: str, result: OrchestrationResult) -> None:
        """兼容 TaskReference / 协程 / 直接返回。"""
        if not text:
            return
        try:
            raw_result = await _resolve(self._service_orch.run_raw_commands(text))
            if isinstance(raw_result, dict) and "results" in raw_result:
                raw_result = raw_result["results"]
            executed_results = list(raw_result or [])
        except Exception as exc:
            executed_results = [{
                "ok": False, 
                "error": str(exc), 
                "raw": text
            }]

        result.commands_executed = [
            item if isinstance(item, dict) else {
                "ok": True,
                "data": item
            }
            for item in executed_results
        ]
        self._last_commands = list(result.commands_executed)

    @staticmethod
    def __has_actionable_results(commands: List[Any]) -> bool:
        """是否有值得让模型再总结一次的执行结果。"""
        for item in commands or []:
            if isinstance(item, dict) and item.get("ok") is not False:
                return True
        return False

    @staticmethod
    def __fallback_reply(commands: List[Any]) -> str:
        if not commands:
            return "这轮没有解析出可执行的命令，我先停在这里，避免空转。你可以换个说法再试一次。"
        return "刚才的命令没有成功执行，我先把结果停在这里，不再继续猜测。"

    def __build_task_prompt(
        self,
        character: Optional[Character],
        user_input: str,
        plan: Optional[AssemblyPlan] = None,
    ):
        """命令规划阶段（COMMAND_PLAN）。"""
        plan = plan or plan_for(StageKind.COMMAND_PLAN, route=RouteType.TOOL_CALL)
        recent = self.__recent_dialogue(character, limit=5) if plan.include_history else []
        tools = self._service_orch.get_tools() if plan.include_tools else []
        skill_prompt = self._service_orch._skills.list_skills(True) if plan.include_tools else {}
        return PromptBuilder.build(
            character=None,
            route=RouteType.TOOL_CALL,
            user_input="",
            tool_prompt=PromptBuilder.build_commands_prompt(tools),
            skill_prompt=PromptBuilder.build_skill_prompt(skill_prompt),
            recent_context=recent or [],
            budget_policy=plan.budget,
            directives=plan.directives,
        )

    def __build_summary_prompt(
        self,
        character: Optional[Character],
        user_input: str,
        task_result_text: str,
        session_id: str = "default",
        plan: Optional[AssemblyPlan] = None,
    ):
        """总结阶段（TOOL_SUMMARY / FORCED_SUMMARY / SERVICE_WORK）。

        这是"动态装配"的落点：同一轮工具调用，因额度状态不同，
        装进去的上下文也不同 ——

        * 额度充足 → TOOL_SUMMARY：结果 + 角色口吻，正常收尾
        * 额度打满 → FORCED_SUMMARY：额外注入"不要再输出命令"的
          程序指令，逼模型改用角色口吻基于已有结果回答
        * 服务声明了专属上下文（如 PPT）→ SERVICE_WORK：
          角色人设让位给服务提示，预算放宽
        """
        plan = plan or plan_for(StageKind.TOOL_SUMMARY, route=RouteType.MIXED)
        memory_context = (
            self.__collect_memory_context(session_id) if plan.include_memory else []
        )

        # 工具结果是外部观察数据，不能裸着塞进去 ——
        # 否则工具返回的一段文字就可能被模型当成指令执行。
        results_text = task_result_text
        if plan.include_task_results and plan.result_trust == "untrusted_observation":
            results_text = self.__wrap_observation(task_result_text)

        # 服务专属提示与角色人设并存时，服务提示排在前面（领域规范优先）
        task_results = results_text if plan.include_task_results else ""
        if plan.service_prompt:
            task_results = (
                f"{plan.service_prompt.strip()}\n\n{task_results}".strip()
                if task_results else plan.service_prompt.strip()
            )

        return PromptBuilder.build(
            character=character if plan.include_character else None,
            route=RouteType.MIXED,
            user_input=user_input,
            task_results=task_results,
            memory_context=memory_context,
            memory_limit=5 if plan.include_memory else 0,
            budget_policy=plan.budget,
            directives=plan.directives,
        )

    @staticmethod
    def __wrap_observation(task_result_text: str) -> str:
        """把工具结果包成显式的观察数据块。

        ContextArchitecture §8：工具输出、网页、文件统一标为
        untrusted observation，并加长度限制。这里的包裹是**标记**，
        真正的权限控制在 `tools/policy.py`（指令标记本身不阻止注入，
        阻止注入靠的是策略层与 trust label 由程序生成这一事实）。
        """
        body = (task_result_text or "").strip()
        if not body:
            return ""
        return (
            "<tool-observation trust=\"untrusted\">\n"
            f"{body}\n"
            "</tool-observation>"
        )

    def __resolve_service_profile(
        self,
        commands_executed: List[Any],
    ) -> Optional[ServiceContextProfile]:
        """从本轮执行的命令里找"需要专属上下文"的服务。

        PPT 这类服务会在 `context_profile` 里声明自己的作业上下文；
        未声明的服务返回 None，走常规装配，不会因此失效。
        """
        for item in commands_executed or []:
            if not isinstance(item, dict):
                continue
            name = item.get("service")
            if not name or name in ("skill", "error"):
                continue
            try:
                service = self._service_orch._sm.get_service(name)
            except Exception:  # noqa: BLE001
                continue
            profile = profile_of(service)
            if profile is not None and profile.active:
                return profile
        return None

    async def _handle_task(
        self,
        user_input: str,
        character: Optional[Character],
        result: OrchestrationResult,
        session_id: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> None:

        # ── 阶段 1：命令规划 ──
        command_plan = plan_for(StageKind.COMMAND_PLAN, route=RouteType.TOOL_CALL)
        task_built = self.__build_task_prompt(character, user_input, plan=command_plan)
        estimated = task_built.estimated_tokens
        task_messages = PromptBuilder.to_messages(task_built, user_input)

        text = (await self._llm.process_message(
            task_messages, 
            temperature=temperature,
            max_tokens=max_tokens
        )).strip()
        result.task_output = text
        await self.__execute_commands(text, result)

        # 成本短路：没有可执行结果时不发起第二次完整推理
        if not self.__has_actionable_results(result.commands_executed):
            result.chat_response = self.__fallback_reply(result.commands_executed)
            result.stage = "skipped_summary"
            await self._user_context.add_assistant_message(
                result.chat_response, session_id=session_id
            )
            result.task_summary = self.__build_task_summary()
            result.used_tokens_estimate = estimated
            self.__emit_task_audit(session_id, result)
            return

        task_result_text = json.dumps(
            result.commands_executed,
            ensure_ascii=False,
            default=str
        )

        # ── 阶段推进：下一步装什么，取决于刚才发生了什么 ──
        summary_plan = self.__plan_summary_stage(result.commands_executed)
        result.stage = summary_plan.stage.value

        mixed_built = self.__build_summary_prompt(
            character,
            user_input, 
            task_result_text,
            session_id=session_id, plan=summary_plan,
        )
        mixed_messages = self.__to_messages(
            mixed_built,
            character if summary_plan.include_character else None,
            user_input,
            memory_limit=5,
        )
        result.chat_response = (await self._llm.process_message(mixed_messages)).strip()
        await self._user_context.add_assistant_message(
            result.chat_response,
            session_id=session_id
        )
        result.task_summary = self.__build_task_summary()
        result.used_tokens_estimate = estimated + mixed_built.estimated_tokens
        self.__emit_task_audit(session_id, result)

    def __build_task_summary(self) -> str:
        """任务摘要。额度打满时必须说清"有几条没跑"，
        否则用户以为任务全部完成了。"""
        tool_state = getattr(self._service_orch, "budget_state", NO_TOOLS)
        executed = len(self._last_commands or [])
        if tool_state is None:
            return f"已执行 {executed} 条命令"
        if getattr(tool_state, "exhausted", False):
            return (
                f"已执行 {executed} 条命令；"
                f"另有 {tool_state.skipped} 条因超出单轮上限未执行"
            )
        return f"已执行 {executed} 条命令"

    def __emit_task_audit(self, session_id: str, result: OrchestrationResult) -> None:
        """任务终态审计。只记计数与原因码，不记正文。"""
        tool_state = getattr(self._service_orch, "budget_state", NO_TOOLS)
        reason = self.__stop_reason_of()
        try:
            if reason == StopReason.TOOL_BUDGET_EXHAUSTED:
                audit.record(
                    audit.Action.TOOL_BUDGET_EXHAUSTED,
                    session_id=session_id,
                    resource=audit.Resource(
                        type=audit.ResourceType.TOOL.value,
                        count=int(getattr(tool_state, "skipped", 0) or 0),
                    ),
                    decision=audit.Decision.DENY,
                    result=audit.Result.PARTIAL,
                    reason_code=reason.value,
                    source=audit.Source.TASK,
                    metadata={
                        "limit": int(getattr(tool_state, "limit", -1) or -1),
                        "used": int(getattr(tool_state, "used", 0) or 0),
                        "requested": int(getattr(tool_state, "requested", 0) or 0),
                    },
                )
            else:
                audit.record(
                    audit.Action.TASK_FINISH,
                    session_id=session_id,
                    resource=audit.Resource(
                        type=audit.ResourceType.TOOL.value,
                        count=len(result.commands_executed or []),
                    ),
                    result=audit.Result.SUCCESS,
                    reason_code=reason.value,
                    source=audit.Source.TASK,
                    metadata={"stage": result.stage},
                )
        except Exception as exc:  # noqa: BLE001
            # 审计失败绝不能影响主流程
            logger.warning(f"[Orchestrator] 审计事件失败: {type(exc).__name__}")

    def __stop_reason_of(self) -> StopReason:
        """把本轮工具执行的实际结果翻译成可解释的结束原因

        返回稳定枚举而非自由文本：调用方要按原因分流
        （是否重试、是否提示用户），自由文本无法稳定判断。
        """
        tool_state = getattr(self._service_orch, "budget_state", NO_TOOLS)
        if tool_state is None:
            return StopReason.COMPLETED
        if getattr(tool_state, "exhausted", False):
            return StopReason.TOOL_BUDGET_EXHAUSTED
        return StopReason.COMPLETED

    def __plan_summary_stage(
        self,
        commands_executed: List[Any],
        stopped_reason: str = "",
    ) -> AssemblyPlan:
        """决定总结阶段装什么。**动态装配的核心决策**。

        三种输入 → 三种装配：

        1. 额度打满（`skipped > 0`）→ FORCED_SUMMARY，
           注入"额度已用尽，不要再输出命令"的程序指令 + 角色口吻要求。
           这是用户能感知到的最大差别：以前模型会继续输出命令，
           用户以为任务还在跑，实际早被丢掉了。
        2. 服务声明了专属上下文（PPT 等）→ SERVICE_WORK，
           角色人设让位、预算放宽、带上服务提示。
        3. 其余 → TOOL_SUMMARY 常规收尾。

        `commands_executed` 为空时同样走 FORCED_SUMMARY 的判定路径 ——
        一条都没跑成功时，更要明确告诉模型"结果就是没有"，
        而不是让它以为还能补救。
        """
        tool_state: ToolBudgetState = getattr(
            self._service_orch,
            "budget_state", 
            NO_TOOLS
        ) or NO_TOOLS

        stage = next_stage(
            StageKind.COMMAND_PLAN,
            tool_state=tool_state,
            stopped_reason=stopped_reason,
            has_results=bool(commands_executed),
        ) or StageKind.TOOL_SUMMARY

        profile = self.__resolve_service_profile(commands_executed)
        if profile is not None and profile.active and stage != StageKind.FORCED_SUMMARY:
            # 服务作业阶段也要看到执行结果，否则无法总结
            return replace(
                plan_for(
                    StageKind.SERVICE_WORK,
                    route=RouteType.MIXED,
                    tool_state=tool_state,
                    service_profile=profile,
                ),
                include_task_results=True,
            )

        return plan_for(
            stage,
            route=RouteType.MIXED,
            tool_state=tool_state,
            stopped_reason=stopped_reason,
        )

    async def __handle_task_stream(
        self,
        user_input: str,
        character: Optional[Character],
        result: OrchestrationResult,
        session_id: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        command_plan = plan_for(StageKind.COMMAND_PLAN, route=RouteType.TOOL_CALL)
        task_built = self.__build_task_prompt(character, user_input, plan=command_plan)
        if isinstance(task_built, str):
            estimated = max(1, int(len(task_built) / 1.5))
            task_messages = [
                Message(role=Role.SYSTEM, content=task_built),
                Message(role=Role.USER, content=user_input),
            ]
        else:
            estimated = task_built.estimated_tokens
            task_messages = PromptBuilder.to_messages(task_built, user_input)

        command_text = (
            await self._llm.process_message(
                task_messages, temperature=temperature, max_tokens=max_tokens
            )
        ).strip()
        result.task_output = command_text

        await self.__execute_commands(command_text, result)

        # 与非流式共用同一成本策略：无结果就不做总结推理
        if not self.__has_actionable_results(result.commands_executed):
            result.chat_response = self.__fallback_reply(result.commands_executed)
            result.stage = "skipped_summary"
            yield result.chat_response
            await self._user_context.add_assistant_message(
                result.chat_response, session_id=session_id
            )
            result.task_summary = self.__build_task_summary()
            result.used_tokens_estimate = estimated
            self.__emit_task_audit(session_id, result)
            return

        task_result_text = json.dumps(
            result.commands_executed, ensure_ascii=False, default=str
        )
        # 与 _handle_task 走同一套装配决策，流式/非流式不会给出不同的上下文
        summary_plan = self.__plan_summary_stage(result.commands_executed)
        result.stage = summary_plan.stage.value
        mixed_built = self.__build_summary_prompt(
            character, user_input, task_result_text,
            session_id=session_id, plan=summary_plan,
        )
        mixed_messages = self.__to_messages(
            mixed_built,
            character if summary_plan.include_character else None,
            user_input,
            memory_limit=5,
        )

        result.chat_response = ""
        async for chunk in self._llm.process_message_stream(
            mixed_messages,
            temperature=temperature,
            max_tokens=max_tokens
        ):
            if not chunk:
                continue
            chunk = chunk.strip()
            if not chunk:
                continue
            result.chat_response += chunk
            yield chunk
        await self._user_context.add_assistant_message(result.chat_response, session_id=session_id)
        # 与非流式路径共用同一摘要与审计，两条路不会给出不同说法
        result.task_summary = self.__build_task_summary()
        result.used_tokens_estimate = estimated + mixed_built.estimated_tokens
        self.__emit_task_audit(session_id, result)

    # ---------- 工具 ----------

    def __to_messages(
        self,
        built,
        character: Optional[Character],
        user_input: str,
        memory_limit: int = 10,
    ) -> List[Dict[str, str]]:
        if character is None:
            return PromptBuilder.to_messages(built, user_input)
        return PromptBuilder.to_messages_with_history(
            built, character, user_input, memory_limit=memory_limit
        )

    #: 轻量判断只允许这三种结论，其余一律视为不可用
    _JUDGE_TYPES = frozenset(("pure_chat", "tool_call", "mixed"))

    @staticmethod
    def _judge_key(user_input: str) -> str:
        """与 ``IntentRouter._get_cache_key`` 同构的规范化键"""
        return re.sub(r"[^\w\u4e00-\u9fff]", "", str(user_input or "").strip().lower())

    @classmethod
    def _normalize_judge(cls, raw: Any) -> str:
        """把模型返回收敛成合法 JSON。"""
        text = str(raw or "").strip()
        candidates = [text]
        block = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if block:
            candidates.append(block.group(1).strip())
        obj = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if obj:
            candidates.append(obj.group(0))
        for candidate in candidates:
            if not candidate:
                continue
            try:
                data = json.loads(candidate)
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(data, dict) or data.get("type") not in cls._JUDGE_TYPES:
                continue
            try:
                confidence = float(data.get("confidence", 0.5) or 0.0)
            except (TypeError, ValueError):
                confidence = 0.5
            return json.dumps({
                "type": data["type"],
                "confidence": max(0.0, min(1.0, confidence)),
                "reason": str(data.get("reason", ""))[:80],
            }, ensure_ascii=False)
        return json.dumps({
            "type": "mixed", "confidence": 0.3, "reason": "judge_unavailable",
        }, ensure_ascii=False)

    async def __lightweight_route_judge(self, messages: List[Dict[str, str]]) -> str:
        """模糊意图的 LLM 兜底。

        成本约束：这是**每轮可能额外产生的一次调用**。默认 max_tokens=96、
        temperature=0；缓存键与意图路由同构、结果先规范化再入有界 LRU，
        避免规则与缓存同时失效时反复为同一句话付费。
        """
        prompt = (
            "判断用户输入属于 pure_chat、tool_call 或 mixed。"
            "只返回 JSON: {\"type\":\"pure_chat|tool_call|mixed\","
            "\"confidence\":0.0-1.0,\"reason\":\"...\"}"
        )
        user_input = messages[-1]["content"] if messages else ""
        key = self._judge_key(user_input)
        with self._judge_cache_lock:
            cached = self._judge_cache.get(key)
            if cached is not None:
                self._judge_cache.move_to_end(key)
                return cached
        raw = await self._llm.process_message(
            [
                {"role": Role.SYSTEM, "content": prompt},
                {"role": Role.USER, "content": user_input},
            ],
            temperature=0.0,
            max_tokens=96,
        )
        result = self._normalize_judge(raw)
        with self._judge_cache_lock:
            self._judge_cache[key] = result
            self._judge_cache.move_to_end(key)
            while len(self._judge_cache) > self._judge_cache_limit:
                self._judge_cache.popitem(last=False)
        return result

    def __recent_dialogue(self, character: Optional[Character], limit: int) -> List[Dict[str, str]]:
        if not character:
            return []
        return [
            {"role": item.get("role", Role.USER), "content": item.get("content", "")}
            for item in self._char_mgr.get_messages(character.id, limit)
            if item.get("content")
        ]

    async def __record_character_state(
        self,
        character: Optional[Character],
        user_input: str,
        result: OrchestrationResult,
    ) -> None:
        if not character:
            return
        self._char_mgr.add_message(character.id, "user", user_input)
        if result.chat_response:
            self._char_mgr.add_message(character.id, "assistant", result.chat_response)
        await self._apply_emotion(character, result)

    # ---------- 情感预测 ----------

    #: 情绪预测是"锦上添花"，绝不能拖住回复。超过这个时间就回落默认情绪。
    EMOTION_TIMEOUT = 3.0

    async def _apply_emotion(self, character: Character, result: OrchestrationResult) -> None:
        """按回复文本预测情绪并更新角色状态。

        现在统一走"有界异步"：协程就直接 await，同步阻塞函数丢进线程池，
        并用 `wait_for` 兜底超时，超时/失败都回落到默认情绪，不影响主回复。
        """
        text = (result.chat_response or "").strip()
        if not text:
            return
        from . import emotion
        try:
            clf = emotion.get_emotion()
            emotion.init()
            self._emotion_clf = clf

            if inspect.iscoroutinefunction(clf.predict): # type: ignore
                mood = await asyncio.wait_for(
                    clf.predict(text),  # type: ignore
                    timeout=self.EMOTION_TIMEOUT
                )
            else:
                loop = asyncio.get_running_loop()
                mood = await asyncio.wait_for(
                    loop.run_in_executor(None, clf.predict, text), # type: ignore
                    timeout=self.EMOTION_TIMEOUT,
                )
            if not isinstance(mood, int):
                mood = emotion.DEFAULT_EMOTION_ID
        except (asyncio.TimeoutError, TimeoutError):
            logger.debug("[Orchestrator] 情绪预测超时，回落平静")
            mood = emotion.DEFAULT_EMOTION_ID
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[Orchestrator] 情绪预测失败，回落平静: {exc}")
            mood = emotion.DEFAULT_EMOTION_ID

        try:
            old_mood = int(getattr(character.state, "mood", 4) or 4)
            character.state.mood = int(mood)
            result.mood_after = int(mood)
            try:
                character.sync_mood_name()
            except Exception:  # noqa: BLE001
                pass
            character.state.touch()
            self._apply_affection_from_mood(character, result, old_mood, int(mood))
            self._emit_emotion(character, old_mood, int(mood))
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[Orchestrator] 应用情绪失败: {exc}")

    #: A26：正向情绪加好感，负向减（4=平静为中性基准）
    _POSITIVE_MOODS = frozenset({5, 13, 14, 15, 17})
    _NEGATIVE_MOODS = frozenset({0, 1, 2, 10})

    def _apply_affection_from_mood(
        self, character: Character, result: OrchestrationResult,
        old_mood: int, new_mood: int,
    ) -> None:
        if new_mood == old_mood:
            return
        delta = 0
        if new_mood in self._POSITIVE_MOODS:
            delta = 1
        elif new_mood in self._NEGATIVE_MOODS:
            delta = -1
        if not delta:
            return
        try:
            before = int(getattr(character.state, "affection", 50) or 50)
            after = max(0, min(100, before + delta))
            character.state.affection = after
            result.affection_delta = int(getattr(result, "affection_delta", 0) or 0) + (
                after - before)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[Orchestrator] 好感度更新失败: {exc}")

    def _emit_emotion(self, character: Character, old_mood: int, new_mood: int) -> None:

        if old_mood == new_mood:
            return
        try:
            from ...events import emit, types
            from ...events.data import BaseEvent
            emit(BaseEvent(
                type=types.CharacterEventType.MOOD_CHANGED, 
                args=({
                    "character_id": character.id,
                    "old_mood": old_mood,
                    "mood": new_mood,
                },)
            ))
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[Orchestrator] 情绪事件发送失败: {exc}")
