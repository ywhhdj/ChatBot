from __future__ import annotations
import random
from typing import Any, Dict, List, Optional

from ..manager.task.decorator import sync_task_scheduler
from ..routes.models import RouteType
from ..characters.models import BuiltPrompt, Character, ContextType, PromptSegment

class PromptBuilder:
    """Build separated prompts for role chat, background task commands and final replies."""

    def __init__(self) -> None:
        self.prompts: Dict[str, str] = {}

    def read_prompts(self, file_path: str) -> None:
        """Read prompts from file."""
        self.prompts = {}
        current_section=""
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    current_section=line[1:-1]
                    continue
                if "#" in line:
                    self.prompts[current_section] = line.strip()

    @sync_task_scheduler
    def load_prompts(self) -> None:
        """Load prompts from file."""
        from ..runtime import RuntimePath
        self.read_prompts(RuntimePath.get_prompts_file_path())

    @classmethod
    def format_memory_context(cls, memory_context: List[Dict[str, str]]) -> str:
        """Format memory context into a string."""
        return "\n\n".join(
            f"## {item['title']}\n{item['content']}"
            for item in memory_context
        )

    @classmethod
    def build(
        cls,
        character: Optional[Character],
        route: RouteType = RouteType.PURE_CHAT,
        user_input: str = "",
        tool_prompt: str = "",
        skill_prompt: str = "",
        memory_context: str|list = "",
        recent_context: Optional[List[Dict[str, str]]] = None,
        memory_limit: int = 10,
        inject_randomness: bool = True,
        task_description: str = "",
        task_results: str = "",
    ) -> BuiltPrompt:
        if isinstance(memory_context, list):
            memory_context = cls.format_memory_context(memory_context)
            
        segments: List[PromptSegment]
        if route == RouteType.TOOL_CALL:
            segments = cls._build_task_segments(
                tool_prompt=tool_prompt,
                skill_prompt=skill_prompt,
                task_description=task_description,
                user_input=user_input,
                recent_context=recent_context or [],
            )
        elif route == RouteType.MIXED:
            segments = cls._build_mixed_segments(
                character=character,
                task_results=task_results,
                memory_context=memory_context,
                memory_limit=memory_limit,
                inject_randomness=inject_randomness,
            )
        else:
            segments = cls._build_chat_segments(
                character=character,
                memory_context=memory_context,
                memory_limit=memory_limit,
                inject_randomness=inject_randomness,
            )

        segments.sort(key=lambda item: item["priority"])
        system_prompt = "\n\n".join(item["content"] for item in segments if item["content"].strip())
        return BuiltPrompt(
            system_prompt=system_prompt,
            segments=segments,
            estimated_tokens=max(1, int(len(system_prompt) / 1.5)),
            character_id=character.id if character else "",
            route=route,
        )

    @classmethod
    def _build_chat_segments(
        cls,
        character: Optional[Character],
        memory_context: str = "",
        memory_limit: int = 10,
        inject_randomness: bool = True,
    ) -> List[PromptSegment]:
        segments: List[PromptSegment] = []
        if not character:
            segments.append({
                "type": ContextType.CHARACTER.value,
                "priority": 10,
                "content": "你是一个温柔、可靠、专注于情感陪伴的中文助手。",
            })
        else:
            attr = character.attributes
            state = character.state
            identity = [
                "## 角色身份",
                f"你叫{attr.name or character.name or '助手'}。",
            ]
            if attr.title:
                identity.append(f"身份/定位: {attr.title}")
            if attr.nickname_for_user:
                identity.append(f"对用户的称呼: {attr.nickname_for_user}")
            segments.append({"type": ContextType.CHARACTER.value, "priority": 10, "content": "\n".join(identity)})

            persona = ["## 性格与表达"]
            for label, value in [
                ("性格", attr.personality),
                ("背景", attr.background),
                ("说话风格", attr.speech_style),
            ]:
                if value:
                    persona.append(f"{label}: {value}")
            if attr.catchphrases:
                persona.append("可偶尔使用的口头禅: " + " / ".join(attr.catchphrases[:5]))
            persona.append(f"当前心情: {cls._describe_mood(state.mood, attr.mood_modifiers)}")
            persona.append(cls._describe_affection(state.affection))
            segments.append({"type": ContextType.CHARACTER.value, "priority": 20, "content": "\n".join(persona)})

            if attr.rules:
                rules = ["## 行为准则"] + [f"- {rule}" for rule in attr.rules[:5]]
                segments.append({"type": ContextType.CHARACTER.value, "priority": 30, "content": "\n".join(rules)})

            if inject_randomness:
                randomness = cls._build_randomness_segment(attr)
                if randomness:
                    segments.append({"type": "randomness", "priority": 40, "content": randomness})

        if memory_context:
            segments.append({
                "type": ContextType.MEMORY.value,
                "priority": 50,
                "content": f"## 可参考记忆\n{memory_context.strip()}",
            })

        segments.append({
            "type": "output_rules",
            "priority": 60,
            "content": "\n".join([
                "## 输出要求",
                "- 只做自然聊天与情感陪伴，不输出工具命令。",
                "- 保持角色风格，回复 1-3 句话，不要超过 50 字。",
                "- 不输出 JSON、Markdown 表格或技术解释，除非用户明确要求。",
            ]),
        })
        return segments

    @classmethod
    def _build_task_segments(
        cls,
        tool_prompt: str,
        skill_prompt: str,
        task_description: str,
        user_input: str,
        recent_context: List[Dict[str, str]],
    ) -> List[PromptSegment]:
        context_lines = []
        for msg in recent_context[-5:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if content:
                context_lines.append(f"{role}: {content}")

        command_rules = [
            "## 后台任务模式",
            "你是后台 agent core，只负责把用户意图转换成可执行命令。",
            "只返回命令本身，不要解释、寒暄、总结或 Markdown。",
            "无法安全执行时返回: error --reason \"原因\"",
            "每行一条命令，最多 10 条。",
        ]
        segments: List[PromptSegment] = [
            {"type": "task_rules", "priority": 10, "content": "\n".join(command_rules)}
        ]
        if context_lines:
            segments.append({
                "type": ContextType.MEMORY.value,
                "priority": 15,
                "content": "## 最近 5 轮上下文\n" + "\n".join(context_lines),
            })
        if tool_prompt:
            segments.append({"type": ContextType.TOOL.value, "priority": 20, "content": tool_prompt.strip()})
        if skill_prompt:
            segments.append({"type": "skill", "priority": 25, "content": skill_prompt.strip()})
        segments.append({
            "type": "task",
            "priority": 30,
            "content": "## 当前任务\n" + (task_description.strip() or user_input.strip()),
        })
        return segments

    @classmethod
    def _build_mixed_segments(
        cls,
        character: Optional[Character],
        task_results: str,
        memory_context: str,
        memory_limit: int,
        inject_randomness: bool,
    ) -> List[PromptSegment]:
        segments = cls._build_chat_segments(character, memory_context, memory_limit, inject_randomness)
        segments = [item for item in segments if item["type"] != "output_rules"]
        if task_results:
            segments.append({
                "type": "task_result",
                "priority": 55,
                "content": f"## 刚完成的后台任务结果\n{task_results.strip()}",
            })
        segments.append({
            "type": "output_rules",
            "priority": 60,
            "content": "\n".join([
                "## 输出要求",
                "- 用角色口吻自然告诉用户任务结果。不要超过50字。",
                "- 不展示内部命令、调用链或长 JSON。",
                "- 回复 1-3 句话，失败时给出可理解的原因。",
            ]),
        })
        return segments

    @classmethod
    def _build_randomness_segment(cls, attr: Any) -> str:
        lines = ["## 本轮表达变化"]
        if getattr(attr, "random_words", None):
            picks = random.sample(attr.random_words, min(len(attr.random_words), 2))
            lines.append("语气词备选: " + ", ".join(picks))
        if getattr(attr, "action_verbs", None):
            picks = random.sample(attr.action_verbs, min(len(attr.action_verbs), 1))
            lines.append("动作描写备选: " + ", ".join(f"*{item}*" for item in picks))
        if len(lines) == 1:
            return ""
        lines.append("自然使用即可，不要堆砌。")
        return "\n".join(lines)

    @classmethod
    def _describe_mood(cls, mood: str, modifiers: Dict[str, str]) -> str:
        if modifiers and mood in modifiers:
            return modifiers[mood]
        return {
            "happy": "心情愉快，语气轻快",
            "sad": "有些低落，语气温柔",
            "angry": "有点不爽，但仍保持克制",
            "excited": "兴奋、有活力",
            "tired": "有些疲惫，表达更轻柔",
        }.get(mood, "平和稳定")

    @classmethod
    def _describe_affection(cls, level: int) -> str:
        if level >= 80:
            return "关系状态: 很亲近，可以主动关心和撒娇。"
        if level >= 60:
            return "关系状态: 比较亲切，可以轻松自然地互动。"
        if level >= 40:
            return "关系状态: 友好自然，不过分亲密。"
        if level >= 20:
            return "关系状态: 礼貌温和，保持一点距离。"
        return "关系状态: 冷淡克制，少说但不伤人。"

    @classmethod
    def build_commands_prompt(cls, tools_list: list[dict], skill_prompt: str = "") -> str:
        lines = [
            "## 可用服务命令",
            "格式: service method --param value",
            "只输出命令，不要解释。参数含空格时使用双引号。",
        ]
        for entry in tools_list or []:
            service_name = str(entry.get("service") or entry.get("name") or "").strip()
            tools = entry.get("tools") or []
            if not service_name or not tools:
                continue
            lines.append(f"### {service_name}")
            for tool in tools:
                func_name = getattr(tool, "name", None) or getattr(tool, "method", None) or ""
                desc = getattr(tool, "description", "") or ""
                params_obj = getattr(tool, "parameters", None)
                props = getattr(params_obj, "properties", {}) if params_obj else {}
                parts = [f"--{name} <{name}>" for name in props.keys()]
                command = f"{service_name} {func_name}".strip()
                if parts:
                    command += " " + " ".join(parts)
                lines.append(f"{command} # {desc}".rstrip())
        if skill_prompt:
            lines.append(skill_prompt.strip())
        return "\n".join(lines)

    @classmethod
    def build_skill_prompt(cls, skills: list[dict]) -> str:
        if not skills:
            return ""
        lines = ["## 可用 Skills", "当需要技能时，只输出: skill --name <name> --des \"<需求描述>\""]
        for skill in skills:
            name = str(skill.get("name", "")).strip()
            description = str(skill.get("description", "")).strip()
            if name:
                lines.append(f"skill --name {name} --des \"{description}\"")
        return "\n".join(lines)

    @classmethod
    def to_messages(cls, built: BuiltPrompt, user_input: str) -> List[Dict[str, str]]:
        return [
            {"role": "system", "content": built.system_prompt},
            {"role": "user", "content": user_input},
        ]

    @classmethod
    def to_messages_with_history(
        cls,
        built: BuiltPrompt,
        character: Character,
        user_input: str,
        memory_limit: int = 10,
    ) -> List[Dict[str, str]]:
        messages = [{"role": "system", "content": built.system_prompt}]
        for msg in character.state.messages[-memory_limit:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_input})
        return messages



prompt_builder = PromptBuilder()
# prompt_builder.load_prompts()
