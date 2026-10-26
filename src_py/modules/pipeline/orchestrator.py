"""角色编排器：在"纯角色聊天"与"后台任务执行"之间分流。
"""
from __future__ import annotations
import json
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, List, Optional

from .. import runtime
from ..models import Role
from .manager import LLM
from ..routes.intent import IntentRouter
from ..routes.models import RouteType
from ..tools.ctl import CLTTool
from ..config.builder import PromptBuilder
from ..characters.models import Character
from .models import OrchestrationResult
from ..logger import logger

LLMCaller = Callable[[List[Dict[str, str]]], Awaitable[str]]
CommandExecutor = Callable[[str], Awaitable[Any]]
from ..types.common import Message


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

    def __init__(self, llm_manager: LLM, emotion_predictor=None) -> None:
        from .. import runtime

        self._char_mgr = runtime.manager.character_manager
        self._llm = llm_manager
        self._router = IntentRouter()
        from ..context.user import UserContext
        
        self._emotion_predictor = emotion_predictor
        self._user_context = UserContext()
        self._last_result = OrchestrationResult()
        self._service_orch = CLTTool()

    # ---------- 非流式 ----------

    async def process(
        self,
        user_input: str,
        force_channel: Optional[RouteType] = None,
        session_id: str = "default",
        source: str = "text",
    ) -> OrchestrationResult:
        from ..config import get_config
        config = get_config()
        if config.llm.max_turns <= 0:
            config.llm.max_turns = 10 #避免无限循环，设置默认值为10轮

        for _ in range(config.llm.max_turns):
            result = OrchestrationResult()
            character = self._char_mgr.get_current()
            result.character_id = character.id if character else ""
            await self._user_context.add_user_message(
                user_input, session_id=session_id, source=source
            )
            channel = force_channel or await self._router.route(
                user_input,
                llm_predict_func=self.__lightweight_route_judge,
            )
            result.route = channel

            if channel in (RouteType.TOOL_CALL, RouteType.MIXED):
                await self._handle_task(user_input, character, result, session_id=session_id)
            else:
                await self.__handle_chat(user_input, character, result, session_id=session_id)

            self.__record_character_state(character, user_input, result)
            result.mood_after = character.state.mood if character else 4
            self._last_result = result
        return result

    # ---------- 流式 ----------

    async def process_stream(
        self,
        user_input: str,
        force_channel: Optional[RouteType] = None,
        session_id: str = "default",
        source: str = "text",
        result_holder: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[str, None]:
        from ..config import get_config
        config = get_config()
        if config.llm.max_turns <= 0:
            config.llm.max_turns = 10 #避免无限循环，设置默认值为10轮
        await self._user_context.add_user_message(
            user_input, session_id=session_id, source=source
        )
        result = OrchestrationResult()
        character = self._char_mgr.get_current()
        result.character_id = character.id if character else ""
        channel = force_channel or await self._router.route(
            user_input,
            llm_predict_func=self.__lightweight_route_judge,
        )
        result.route = channel
        
        for _ in range(config.llm.max_turns):

            if result_holder is not None:
                result_holder["result"] = result  # 先放进去，异常时调用方也能拿到部分信息
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
                    async for chunk in self.__handle_task_stream(
                        user_input, character, result, session_id=session_id
                    ):
                        yield chunk
                else:
                    tracer.phase_change("answering")
                    async for chunk in self.__handle_chat_stream(
                        user_input, character, result, session_id=session_id
                    ):
                        yield chunk
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
                self.__record_character_state(character, user_input, result)
                result.mood_after = character.state.mood if character else 4

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
        built = self.__build_chat_prompt(character, user_input)
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
        built = self.__build_chat_prompt(character, user_input)
        messages = self.__to_messages(built, character, user_input, memory_limit=10)
        result.chat_response = ""
        ref = await self._llm.process_message_stream(
            messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        async for chunk in ref.data:
            if not chunk:
                continue
            chunk = chunk.strip()
            if not chunk:
                continue
            result.chat_response += chunk
            yield chunk
        await self._user_context.add_assistant_message(result.chat_response, session_id=session_id)
        result.used_tokens_estimate = built.estimated_tokens

    def __build_chat_prompt(self, character: Optional[Character], user_input: str):
        memory_context = self._user_context.get_current_messages()
        return PromptBuilder.build(
            character=character,
            route=RouteType.PURE_CHAT,
            user_input=user_input,
            memory_context=memory_context,
            memory_limit=10,
            inject_randomness=True,
        )

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

    def __build_task_prompt(self, character: Optional[Character], user_input: str):
        """走 PromptBuilder 的三上下文分离，而不是直接调私有方法。"""
        recent = self.__recent_dialogue(character, limit=5)
        tools = self._service_orch.get_tools()
        skill_prompt = self._service_orch._skills.list_skills(True)
        return PromptBuilder.build(
            character=None,
            route=RouteType.TOOL_CALL,
            user_input="",
            tool_prompt=PromptBuilder.build_commands_prompt(tools),
            skill_prompt=PromptBuilder.build_skill_prompt(skill_prompt),
            recent_context=recent or [],
        )

    def __build_mixed_prompt(
        self, character: Optional[Character],
        user_input: str,
        task_result_text: str
    ):
        memory_context = self._user_context.get_current_messages()
        return PromptBuilder.build(
            character=character,
            route=RouteType.MIXED,
            user_input=user_input,
            task_results=task_result_text,
            memory_context=memory_context,
            memory_limit=5,
        )

    async def _handle_task(
        self,
        user_input: str,
        character: Optional[Character],
        result: OrchestrationResult,
        session_id: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> None:

        task_built = self.__build_task_prompt(character, user_input)
        estimated = task_built.estimated_tokens
        task_messages = PromptBuilder.to_messages(task_built, user_input)

        text = (await self._llm.process_message(
            task_messages, 
            temperature=temperature,
            max_tokens=max_tokens
        )).strip()
        result.task_output = text
        await self.__execute_commands(text, result)
        task_result_text = json.dumps(
            result.commands_executed,
            ensure_ascii=False,
            default=str
        )
        mixed_built = self.__build_mixed_prompt(character, user_input, task_result_text)
        mixed_messages = self.__to_messages(mixed_built, character, user_input, memory_limit=5)
        result.chat_response = (await self._llm.process_message(mixed_messages)).strip()
        await self._user_context.add_assistant_message(
            result.chat_response,
            session_id=session_id
        )
        result.task_summary = f"已执行 {len(result.commands_executed)} 条命令"
        result.used_tokens_estimate = estimated + mixed_built.estimated_tokens

    async def __handle_task_stream(
        self,
        user_input: str,
        character: Optional[Character],
        result: OrchestrationResult,
        session_id: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        task_built = self.__build_task_prompt(character, user_input)
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

        task_result_text = json.dumps(
            result.commands_executed, ensure_ascii=False, default=str
        )
        mixed_built = self.__build_mixed_prompt(character, user_input, task_result_text)
        mixed_messages = self.__to_messages(mixed_built, character, user_input, memory_limit=5)

        result.chat_response = ""
        ref = await self._llm.process_message_stream(
            mixed_messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        async for chunk in ref.data:
            if not chunk:
                continue
            chunk = chunk.strip()
            if not chunk:
                continue
            result.chat_response += chunk
            yield chunk
        await self._user_context.add_assistant_message(result.chat_response, session_id=session_id)
        result.task_summary = f"已执行 {len(result.commands_executed)} 条命令"
        result.used_tokens_estimate = estimated + mixed_built.estimated_tokens

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

    async def __lightweight_route_judge(self, messages: List[Dict[str, str]]) -> str:
        prompt = (
            "判断用户输入属于 pure_chat、tool_call 或 mixed。"
            "只返回 JSON: {\"type\":\"pure_chat|tool_call|mixed\","
            "\"confidence\":0.0-1.0,\"reason\":\"...\"}"
        )
        user_input = messages[-1]["content"] if messages else ""
        return await self._llm.process_message([
            {"role": Role.SYSTEM, "content": prompt},
            {"role": Role.USER, "content": user_input},
        ])

    def __recent_dialogue(self, character: Optional[Character], limit: int) -> List[Dict[str, str]]:
        if not character:
            return []
        return [
            {"role": item.get("role", Role.USER), "content": item.get("content", "")}
            for item in self._char_mgr.get_messages(character.id, limit)
            if item.get("content")
        ]

    def __record_character_state(
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
        self._apply_emotion(character, result)

    # ---------- A23–A28：情感预测 ----------

    def _apply_emotion(self, character: Character, result: OrchestrationResult) -> None:
        """按回复文本预测情绪并更新角色状态。"""
        text = (result.chat_response or "").strip()
        if not text:
            return
        try:
            from ..pipeline.emotion.predictor import (
                DEFAULT_EMOTION_ID,
                LLMEmotionClassifier,
            )

            clf = getattr(self, "_emotion_clf", None)
            if clf is None:
                clf = LLMEmotionClassifier()
                self._emotion_clf = clf

            fut = runtime.manager.task_manager.submit(clf.classify, text) # type: ignore
            mood = fut.result() if fut is not None else clf.classify(text)
            if not isinstance(mood, int):
                mood = DEFAULT_EMOTION_ID
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[Orchestrator] 情绪预测失败，回落平静: {exc}")
            try:
                from ..pipeline.emotion.predictor import DEFAULT_EMOTION_ID
            except Exception:  # noqa: BLE001
                DEFAULT_EMOTION_ID = 4  # noqa: N806
            mood = DEFAULT_EMOTION_ID

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
            from ..events import emit, types
            from ..events.data import BaseEvent
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
