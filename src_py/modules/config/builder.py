"""Prompt 构建：三上下文分离（角色 / 工具 / 用户）"""

from __future__ import annotations

import random
import re
import threading
from typing import Any, Dict, List, Optional, Union

from src_py.modules.models import Role

from ..routes.models import RouteType
from ..characters.models import BuiltPrompt, Character, ContextType, PromptSegment

# CJK 字符大致 1 字 ≈ 1 token；拉丁文约 4 字符 ≈ 1 token
_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")


class PromptBuilder:
    """按路由组装分离的 system prompt。"""

    # ---------- 记忆格式化 ----------

    @classmethod
    def format_memory_context(
        cls, memory_context: Union[str, List[Dict[str, Any]]]
    ) -> str:
        """同时兼容 `{"title","content"}` 与 `{"role","content"}` 两种形态。

        UserContext.get_current_messages() 产出的是 role/content，
        原实现硬取 item['title'] -> KeyError。
        """
        if isinstance(memory_context, str):
            return memory_context
        lines: List[str] = []
        for item in memory_context:
            if not isinstance(item, dict):
                continue
            title = item.get("title") or item.get("role") or item.get("name") or "上下文"
            content = item.get("content", "")
            if content:
                lines.append(f"## {title}\n{content}")
        return "\n\n".join(lines)

    # ---------- 主入口 ----------

    @classmethod
    def build(
        cls,
        character: Optional[Character],
        route: RouteType = RouteType.PURE_CHAT,
        user_input: str = "",
        tool_prompt: str = "",
        skill_prompt: str = "",
        memory_context: Union[str, List[Dict[str, Any]], None] = None,
        recent_context: Optional[List[Dict[str, str]]] = None,
        memory_limit: int = 10,
        inject_randomness: bool = True,
        task_description: str = "",
        task_results: str = "",
    ) -> BuiltPrompt:
        memory_text = cls.format_memory_context(memory_context or "")

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
                memory_context=memory_text,
                memory_limit=memory_limit,
                inject_randomness=inject_randomness,
            )
        else:
            segments = cls._build_chat_segments(
                character=character,
                memory_context=memory_text,
                memory_limit=memory_limit,
                inject_randomness=inject_randomness,
            )

        segments.sort(key=lambda item: item["priority"])
        system_prompt = "\n\n".join(item["content"] for item in segments if item["content"].strip())
        return BuiltPrompt(
            system_prompt=system_prompt,
            segments=segments,
            estimated_tokens=cls.estimate_tokens(system_prompt),
            character_id=character.id if character else "",
            route=route,
        )

    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        """区分 CJK 与拉丁字符估算 token。"""
        if not text:
            return 0
        cjk = len(_CJK_RE.findall(text))
        others = len(text) - cjk
        return max(1, int(cjk + others / 4))

    # ---------- 各通道片段 ----------

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
            segments.append(PromptSegment(
                type=ContextType.CHARACTER.value,
                priority=10,
                content="你是一个温柔、可靠、专注于情感陪伴的中文助手。",
            ))
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
            segments.append(PromptSegment(
                type=ContextType.CHARACTER.value,
                priority=10,
                content="\n".join(identity),
            ))

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
            # C16：state.mood 是 int，要先转成情绪名才能命中 mood_modifiers
            persona.append(f"当前心情: {cls._describe_mood(state.mood, attr.mood_modifiers)}")
            persona.append(cls._describe_affection(state.affection))
            segments.append(PromptSegment(
                type=ContextType.CHARACTER.value,
                priority=20,
                content="\n".join(persona),
            ))

            if attr.rules:
                rules = ["## 行为准则"] + [f"- {rule}" for rule in attr.rules[:5]]
                segments.append(PromptSegment(
                    type=ContextType.CHARACTER.value,
                    priority=30,
                    content="\n".join(rules),
                ))

            if inject_randomness:
                randomness = cls._build_randomness_segment(attr)
                if randomness:
                    segments.append(PromptSegment(
                        type="randomness",
                        priority=40,
                        content=randomness,
                    ))

        if memory_context:
            segments.append(PromptSegment(
                type=ContextType.MEMORY.value,
                priority=50,
                content=f"## 可参考记忆\n{memory_context.strip()}",
            ))

        segments.append(PromptSegment(
            type="output_rules",
            priority=60,
            content="\n".join([
                "## 输出要求",
                "- 只做自然聊天与情感陪伴，不输出工具命令。",
                "- 保持角色风格，回复 1-3 句话，不要超过 50 字。",
                "- 不输出 JSON、Markdown 表格或技术解释，除非用户明确要求。",
            ]),
        ))
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
            role = msg.get("role", Role.USER)
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
            PromptSegment(
                type="task_rules", 
                priority=10, 
                content="\n".join(command_rules),
            ),
        ]
        if context_lines:
            segments.append(PromptSegment(
                type=ContextType.MEMORY.value,
                priority=15,
                content="## 最近 5 轮上下文\n" + "\n".join(context_lines),
            ))
        if tool_prompt:
            segments.append(PromptSegment(
                type=ContextType.TOOL.value,
                priority=20,
                content=tool_prompt.strip(),
            ))
        if skill_prompt:
            segments.append(PromptSegment(
                type="skill",
                priority=25,
                content=skill_prompt.strip(),
            ))
        segments.append(PromptSegment(
            type="task",
            priority=30,
            content="## 当前任务\n" + (task_description.strip() or user_input.strip()),
        ))
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
        segments = cls._build_chat_segments(
            character, memory_context, memory_limit, inject_randomness
        )
        segments = [item for item in segments if item["type"] != "output_rules"]
        if task_results:
            segments.append(PromptSegment(
                type="task_result",
                priority=55,
                content=f"## 刚完成的后台任务结果\n{task_results.strip()}",
            ))
        segments.append(PromptSegment(
            type="output_rules",
            priority=60,
            content="\n".join([
                "## 输出要求",
                "- 用角色口吻自然告诉用户任务结果。不要超过50字。",
                "- 不展示内部命令、调用链或长 JSON。",
                "- 回复 1-3 句话，失败时给出可理解的原因。",
            ]),
        ))
        return segments

    # ---------- 片段工具 ----------

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
    def _describe_mood(cls, mood: Any, modifiers: Optional[Dict[str, str]] = None) -> str:
        """C16：state.mood 是 int，modifiers 的 key 是字符串，必须转换后再查。

        int  -> 用 emotion_map 转成情绪名（"高兴"），再查 modifiers
        str  -> 直接查 modifiers
        都没有 -> 用内置兜底表
        """
        modifiers = modifiers or {}
        mood_name: Optional[str] = None

        if isinstance(mood, bool):
            mood = int(mood)

        if isinstance(mood, int):
            try:
                from ..characters.presets import id_to_name
                mood_name = id_to_name(mood)
            except Exception:
                mood_name = None
        elif isinstance(mood, str):
            mood_name = mood.strip()

        if mood_name and mood_name in modifiers:
            return modifiers[mood_name]

        # 情绪名也可能是英文键（happy/sad...），再试一次常见映射
        alias = {
            "高兴": "happy",
            "开心": "happy",
            "平静": "neutral",
            "生气": "angry",
            "难过": "sad",
            "伤心": "sad",
            "兴奋": "excited",
            "疲惫": "tired",
            "害羞": "shy",
            "惊讶": "surprised",
        }.get(mood_name or "", mood_name)
        if alias and alias in modifiers:
            return modifiers[alias]

        return {
            "happy": "心情愉快，语气轻快",
            "sad": "有些低落，语气温柔",
            "angry": "有点不爽，但仍保持克制",
            "excited": "兴奋、有活力",
            "tired": "有些疲惫，表达更轻柔",
        }.get(alias or "", f"当前情绪: {mood_name or mood}")

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

    # ---------- 命令文档 ----------

    @classmethod
    def build_commands_prompt(cls, tools_list: list, skill_prompt: str = "") -> str:
        """同时兼容 dict 与对象两种 tool 形态。"""
        lines = [
            "## 可用服务命令",
            "格式: service method --param value",
            "只输出命令，不要解释。参数含空格时使用双引号。",
        ]

        def _get(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        for entry in tools_list or []:
            service_name = str(_get(entry, "service") or _get(entry, "name") or "").strip()
            tools = _get(entry, "tools") or []
            if not service_name or not tools:
                continue
            lines.append(f"### {service_name}")
            for tool in tools:
                func_name = _get(tool, "name") or _get(tool, "method") or ""
                desc = _get(tool, "description", "") or ""
                params_obj = _get(tool, "parameters")
                props = _get(params_obj, "properties", {}) if params_obj else {}
                if not isinstance(props, dict):
                    props = {}
                parts = [f"--{name} <{name}>" for name in props.keys()]
                command = f"{service_name} {func_name}".strip()
                if parts:
                    command += " " + " ".join(parts)
                lines.append(f"{command} # {desc}".rstrip())
        if skill_prompt:
            lines.append(skill_prompt.strip())
        return "\n".join(lines)

    @classmethod
    def build_skill_prompt(cls, skills: Dict[str, str]) -> str:
        if not skills:
            return ""
        lines = [
            "## 可用 Skills",
            '只在需要技能时输出: skill --id <id> --des "<需求描述>"',
        ]
        for skill_id, description in skills.items():
            lines.append(f'skill --id {skill_id} --des "{description}"')
        return "\n".join(lines)

    # ---------- 消息组装 ----------

    @classmethod
    def to_messages(cls, built: BuiltPrompt, user_input: str) -> List[Dict[str, str]]:
        return [
            {
                "role": Role.SYSTEM,
                "content": built.system_prompt
            },
            {
                "role": Role.USER,
                "content": user_input
            },
        ]

    @classmethod
    def to_messages_with_history(
        cls,
        built: BuiltPrompt,
        character: Character,
        user_input: str,
        memory_limit: int = 10,
    ) -> List[Dict[str, str]]:
        messages = [{
            "role": Role.SYSTEM,
            "content": built.system_prompt
        }]
        for msg in character.state.messages[-memory_limit:]:
            role = msg.get("role", Role.USER)
            content = msg.get("content", "")
            if role in {Role.USER, Role.ASSISTANT} and content:
                messages.append({
                    "role": role,
                    "content": content
                })
        messages.append({
            "role": Role.USER,
            "content": user_input
        })
        return messages


prompt_builder = PromptBuilder()
