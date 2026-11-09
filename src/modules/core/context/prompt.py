"""Prompt 构建：三上下文分离（角色 / 工具 / 用户）"""

from __future__ import annotations

import random
import re
import threading
from typing import Any, Dict, List, Optional, Sequence, Union

from ...models import Role

from ..routes.models import RouteType
from ...characters.models import BuiltPrompt, Character, ContextType, PromptSegment
from .budget import (
    BudgetPolicy,
    apply_budget,
    estimate_tokens as _estimate_tokens,
)

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
        budget_policy: Optional[BudgetPolicy] = None,
        directives: Optional[Sequence[str]] = None,
    ) -> BuiltPrompt:
        """装配 prompt。**纯构建**：不读全局状态、不发请求、不写文件。

        1. **分段**：按路由产出 segments，每段带 type/priority/content；
        2. **预算**：`apply_budget()` 决定保留/丢弃/截断，产出报告；
        3. **组装**：按 priority 升序拼 system_prompt，计 token 返回。

        `directives`（动态装配）
        ───────────────────────
        由**程序生成**的阶段指令，优先级高于角色人设与记忆，
        用于"工具额度已耗尽，请改用角色口吻总结"这类运行时状态告知。

        为什么必须是独立参数而不是塞进 user_input：
        模型不该也无法区分"用户说的话"和"系统要求的约束"。
        把指令混进用户输入，等于让外部内容有机会自我声明信任级别 ——
        违反 ContextArchitecture §8（trust label 由程序产生）。
        """
        memory_text = cls.format_memory_context(
            cls.limit_memory(memory_context, memory_limit)
        )

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

        # 1.5) 阶段指令：优先级 5，仅高于角色身份（10）
        segments.extend(cls._build_directive_segments(directives)) # type:ignore

        # 2) 预算裁剪（默认策略；调用方可传入自定义）
        kept, report = apply_budget(segments, budget_policy or BudgetPolicy())

        # 3) 组装（apply_budget 已按 priority 升序返回）
        system_prompt = "\n\n".join(
            item["content"] for item in kept
            if isinstance(item, dict) and item.get("content", "").strip()
        )
        return BuiltPrompt(
            system_prompt=system_prompt,
            segments=kept,
            estimated_tokens=cls.estimate_tokens(system_prompt),
            character_id=character.id if character else "",
            route=route,
            budget=report.as_dict(),
        )

    @classmethod
    def _build_directive_segments(
        cls,
        directives: Optional[Sequence[str]]
    ) -> List[Dict[str, Any]]:
        """阶段指令段。

        优先级 5 —— 高于角色身份（10）与记忆（50），
        低于将来可能加入的系统安全策略（若有的话排 1）。

        多条指令合并成一段而不是各占一段：它们是同一次装配的
        一组约束，拆开会让预算裁剪有机会丢掉其中一条而保留另一条，
        造成"知道额度耗尽但不知道要总结"的半截状态。
        """
        lines = [str(d).strip() for d in (directives or []) if str(d).strip()]
        if not lines:
            return []
        return [{
            "type": "directive",
            "priority": 5,
            "content": "## 本轮执行约束\n" + "\n".join(f"- {line}" for line in lines),
        }]

    # ---------- 记忆条数约束 ----------

    @classmethod
    def limit_memory(
        cls,
        memory_context: Union[str, List[Dict[str, Any]], None],
        memory_limit: int = 10,
    ) -> Union[str, List[Dict[str, Any]], None]:
        """按条数裁剪记忆（token 预算之外的第一道闸）。

        `memory_limit <= 0` 视为不限制，保持向后兼容。
        """
        if not isinstance(memory_context, list) or memory_limit is None or memory_limit <= 0:
            return memory_context
        if len(memory_context) <= memory_limit:
            return memory_context
        # 保留**最近**的：记忆片段里最新的通常最相关
        return list(memory_context[-memory_limit:])

    # ---------- 单段构建（可独立测试与计 token） ----------

    @classmethod
    def build_segment(
        cls,
        type_: str,
        priority: int,
        content: str,
    ) -> Dict[str, Any]:
        """构造单个片段。

        纯化后每一段都能单独断言"类型/优先级/内容"，
        不用为了测记忆段而先造一个完整角色。
        token 用量走 `context.budget.estimate_tokens(content)` 单独统计 ——
        不塞进片段里，避免 PromptSegment 形状随调用点漂移。
        """
        return {
            "type": type_,
            "priority": priority,
            "content": content,
        }

    @classmethod
    def segment_tokens(cls, segment: Dict[str, Any]) -> int:
        """单个片段的 token 用量（供测试与日志）。"""
        return cls.estimate_tokens(str(segment.get("content", "")))

    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        """区分 CJK 与拉丁字符估算 token"""
        return _estimate_tokens(text)

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
                from ...characters.presets import id_to_name
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
        # shell 兜底：模型直接写原生命令原文，不需要 `shell --command` 包装。
        # 平台差异由后端映射，删除/提权/拼接/越界由后端确定性拒绝。
        lines.extend([
            "",
            "## 通用 Shell 命令（兜底）",
            "除上面的服务命令、skill、error 之外，其余命令直接写原生命令原文，",
            "不要加 shell 前缀，也不要写 --command 之类的包装。",
            "示例：cd docs / ls -la / dir / mkdir report / cat notes.txt / type notes.txt / pwd / echo hello",
            "命令只在当前工作区内执行；禁止 rm/del/rd/format/sudo 等删除与提权命令，",
            "禁止管道、重定向与命令拼接，禁止访问工作区外的路径。",
            "系统差异由后端按平台映射（dir↔ls、type↔cat、copy↔cp、move↔mv、cls↔clear）。",
        ])
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
