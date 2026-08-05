from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, List, Optional

from src_py.modules.pipeline.manager import LLM

from ..routes.intent import IntentRouter
from ..routes.models import RouteType
from ..tools.ctl import ServiceOrchestrator
from ..config.builder import PromptBuilder
from ..manager.character import character_manager
from .models import Character


LLMCaller = Callable[[List[Dict[str, str]]], Awaitable[str]]
CommandExecutor = Callable[[str], Awaitable[Any]]


@dataclass
class OrchestrationResult:
    route: RouteType = RouteType.PURE_CHAT
    chat_response: str = ""
    task_output: str = ""
    commands_executed: List[Dict[str, Any]] = field(default_factory=list)
    task_summary: str = ""
    used_tokens_estimate: int = 0
    character_id: str = ""
    mood_after: str = ""
    affection_delta: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "route": self.route.value,
            "chat_response": self.chat_response,
            "task_output": self.task_output,
            "commands_executed": self.commands_executed,
            "task_summary": self.task_summary,
            "used_tokens_estimate": self.used_tokens_estimate,
            "character_id": self.character_id,
            "mood_after": self.mood_after,
            "affection_delta": self.affection_delta,
        }


class CharacterOrchestrator:
    """Route user input between clean role chat and a lean background task agent."""

    def __init__(self, llm_manager: LLM) -> None:
        self._char_mgr = character_manager
        self._llm = llm_manager
        self._router = IntentRouter()
        from ..context.user import UserContext
        self._user_context = UserContext()
        self._last_result = OrchestrationResult()
        self._service_orch=ServiceOrchestrator()

    async def process(
        self,
        user_input: str,
        force_channel: Optional[RouteType] = None,
        session_id: str = "default",
        source: str = "text",
    ) -> OrchestrationResult:
        result = OrchestrationResult()
        character = self._char_mgr.get_current()
        result.character_id = character.id if character else ""
        await self._user_context.add_user_message(user_input, session_id=session_id,source=source)
        channel = force_channel or await self._router.route(
            user_input,
            llm_predict_func=self._lightweight_route_judge,
        )
        result.route = channel

        if channel == RouteType.TOOL_CALL:
            await self._handle_task(user_input, character, result, session_id=session_id)
        elif channel == RouteType.MIXED:
            
            await self._handle_task(user_input, character, result, session_id=session_id)
        else:
            await self._handle_chat(user_input, character, result, session_id=session_id)

        self._record_character_state(character, user_input, result)
        result.mood_after = character.state.mood if character else ""
        self._last_result = result
        return result

    async def process_stream(
        self,
        user_input: str,
        force_channel: Optional[RouteType] = None,
        session_id: str = "default",
        source: str = "text",
    ) -> AsyncGenerator[str, None]:
        result = OrchestrationResult()
        character = self._char_mgr.get_current()
        result.character_id = character.id if character else ""
        await self._user_context.add_user_message(user_input, session_id=session_id,source=source)
        channel = force_channel or await self._router.route(
            user_input,
            llm_predict_func=self._lightweight_route_judge,
        )
        result.route = channel

        if channel == RouteType.TOOL_CALL:
            await self._handle_task(user_input, character, result, session_id=session_id)
        elif channel == RouteType.MIXED:
            
            await self._handle_task(user_input, character, result, session_id=session_id)
        else:
            async for chunk in self._handle_chat_stream(user_input, character, result, session_id=session_id):
                yield chunk

        self._record_character_state(character, user_input, result)
        result.mood_after = character.state.mood if character else ""
        self._last_result = result

    async def _handle_chat(
        self,
        user_input: str,
        character: Optional[Character],
        result: OrchestrationResult,
        session_id: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> None:
        memory_context = self._user_context.get_current_messages()
        built = PromptBuilder.build(
            character=character,
            route=RouteType.PURE_CHAT,
            user_input=user_input,
            memory_context=memory_context,
            memory_limit=10,
            inject_randomness=True,
        )
        messages = PromptBuilder.to_messages_with_history(
            built,
            character,
            user_input,
            memory_limit=10,
        ) if character else PromptBuilder.to_messages(built, user_input)
        result.chat_response = (await self._llm.process_message(messages, temperature=temperature, max_tokens=max_tokens)).strip()
        await self._user_context.add_assistant_message(result.chat_response, session_id=session_id)
        result.used_tokens_estimate = built.estimated_tokens

    async def _handle_task(
        self,
        user_input: str,
        character: Optional[Character],
        result: OrchestrationResult,
        session_id: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> None:
        recent = self._recent_dialogue(character, limit=5)
        task_built = self._service_orch._build_system_prompt(recent)
        command_text = (await self._llm.process_message(
            PromptBuilder.to_messages(task_built, user_input),
            temperature=temperature,
            max_tokens=max_tokens,
        )).strip()
        result.task_output = command_text

        executed_results: List[Dict[str, Any]] = []
        if command_text:
            try:
                raw_result = await self._service_orch.run_raw_commands(command_text).wait_async()
                if isinstance(raw_result, dict) and "results" in raw_result:
                    raw_result = raw_result["results"]
                    executed_results = raw_result
            except Exception as exc:
                executed_results = [{"ok": False, "error": str(exc), "raw": command_text}]
        result.commands_executed = [item if isinstance(item, dict) else {
            "ok": True, 
            "data": item
        } for item in executed_results]

        task_result_text = json.dumps(result.commands_executed, ensure_ascii=False, default=str)
        memory_context = self._user_context.get_current_messages()
        mixed_built = PromptBuilder.build(
            character=character,
            route=RouteType.MIXED,
            user_input=user_input,
            task_results=task_result_text,
            memory_context=memory_context,
            memory_limit=5,
        )
        mixed_messages = PromptBuilder.to_messages_with_history(
            mixed_built,
            character,
            user_input,
            memory_limit=5,
        ) if character else PromptBuilder.to_messages(mixed_built, user_input)
        result.chat_response = (await self._llm.process_message(mixed_messages)).strip()
        await self._user_context.add_assistant_message(result.chat_response, session_id=session_id)
        result.task_summary = f"已执行 {len(result.commands_executed)} 条命令"
        result.used_tokens_estimate = task_built.estimated_tokens + mixed_built.estimated_tokens

    async def _handle_task_stream(
        self,
        user_input: str,
        character: Optional[Character],
        result: OrchestrationResult,
        session_id: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        recent = self._recent_dialogue(character, limit=5)
        task_built = self._service_orch._build_system_prompt(recent)
        command_text = (await self._llm.process_message(PromptBuilder.to_messages(task_built, user_input))).strip()
        result.task_output = command_text

        executed_results: List[Dict[str, Any]] = []
        if command_text:
            try:
                raw_result = await self._service_orch.run_raw_commands(command_text).wait_async()
                if isinstance(raw_result, dict) and "results" in raw_result:
                    raw_result = raw_result["results"]
                    executed_results=raw_result
            except Exception as exc:
                executed_results = [{"ok": False, "error": str(exc), "raw": command_text}]
        result.commands_executed = [item if isinstance(item, dict) else {
            "ok": True, 
            "data": item
        } for item in executed_results]

        task_result_text = json.dumps(result.commands_executed, ensure_ascii=False, default=str)
        memory_context = self._user_context.get_current_messages()
        mixed_built = PromptBuilder.build(
            character=character,
            route=RouteType.MIXED,
            user_input=user_input,
            task_results=task_result_text,
            memory_context=memory_context,
            memory_limit=5,
        )
        mixed_messages = PromptBuilder.to_messages_with_history(
            mixed_built,
            character,
            user_input,
            memory_limit=5,
        ) if character else PromptBuilder.to_messages(mixed_built, user_input)
        result.chat_response = ""
        ref = await self._llm.process_message_stream(mixed_messages, temperature=temperature, max_tokens=max_tokens)
        async for chunk in ref.data:
            if chunk:
                chunk = chunk.strip()
                result.chat_response += chunk
                yield chunk
        await self._user_context.add_assistant_message(result.chat_response, session_id=session_id)
        result.task_summary = f"已执行 {len(result.commands_executed)} 条命令"
        result.used_tokens_estimate = task_built.estimated_tokens + mixed_built.estimated_tokens

    async def _handle_chat_stream(
        self,
        user_input: str,
        character: Optional[Character],
        result: OrchestrationResult,
        session_id: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        memory_context = self._user_context.get_current_messages()
        built = PromptBuilder.build(
            character=character,
            route=RouteType.PURE_CHAT,
            user_input=user_input,
            memory_context=memory_context,
            memory_limit=10,
            inject_randomness=True,
        )
        messages = PromptBuilder.to_messages_with_history(
            built,
            character,
            user_input,
            memory_limit=10,
        ) if character else PromptBuilder.to_messages(built, user_input)
        result.chat_response = ""
        ref = await self._llm.process_message_stream(messages, temperature=temperature, max_tokens=max_tokens)
        async for chunk in ref.data:
            if chunk:
                chunk = chunk.strip()
                result.chat_response += chunk
                yield chunk
        await self._user_context.add_assistant_message(result.chat_response, session_id=session_id)
        result.used_tokens_estimate = built.estimated_tokens

    async def _lightweight_route_judge(self, messages: List[Dict[str, str]]) -> str:
        prompt = (
            "判断用户输入属于 pure_chat、tool_call 或 mixed。"
            "只返回 JSON: {\"type\":\"pure_chat|tool_call|mixed\",\"reason\":\"...\"}"
        )
        user_input = messages[-1]["content"] if messages else ""
        return await self._llm.process_message([
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_input},
        ])


    def _recent_dialogue(self, character: Optional[Character], limit: int) -> List[Dict[str, str]]:
        if not character:
            return []
        return [
            {"role": item.get("role", "user"), "content": item.get("content", "")}
            for item in self._char_mgr.get_messages(character.id, limit)
            if item.get("content")
        ]

    def _record_character_state(
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
        self._update_affection_from_interaction(character, user_input, result)

    def _update_affection_from_interaction(
        self,
        character: Character,
        user_input: str,
        result: OrchestrationResult,
    ) -> None:
        text = user_input.lower()
        delta = 0
        if any(word in text for word in ["谢谢", "辛苦", "爱你", "真好", "开心", "哈哈"]):
            delta += 1
        if any(word in text for word in ["讨厌", "烦", "没用", "生气", "难过"]):
            delta -= 1
        if result.commands_executed:
            delta += 1 if all(item.get("ok", False) for item in result.commands_executed) else -1
        if delta:
            self._char_mgr.update_affection(character.id, delta)
            result.affection_delta = delta
