"""上下文压缩"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Generic, List, Optional, TypeVar

from ..config.builder import prompt_builder
from ..logger import logger
from ..models import Role,TimeRange,CompressedContext,MessageContext

T=TypeVar("T",bound=MessageContext)



# C106：兜底模板，prompts 里没有 compressor 时使用
_FALLBACK_TEMPLATE = """请将以下对话压缩为结构化摘要。

要求：
1. 保留关键事实、用户偏好与已做决策
2. 丢弃寒暄与重复内容
3. 以 JSON 输出：{"summary": "...", "key_points": [{"topic": "...", "content": "...", "importance": 1-5}], "decisions": [], "pending_items": [], "user_intent": "..."}

对话内容：
${dialogue}
"""


class ContextCompressor(Generic[T]):
    def __init__(self, llm_manager: Any = None) -> None:
        self.llm_manager = llm_manager
        self.dialogue_placeholder = "${dialogue}"
        self._compression_timeout = 15.0
        self.SYSTEM_PROMPT = (
            "你是一个专业的对话压缩助手，擅长将长对话压缩为结构化摘要。核心原则：\n"
            "1. 保持信息的准确性和完整性\n"
            "2. 按时间顺序组织内容\n"
            "3. 突出关键决策和行动项\n"
            "4. 保留用户的核心诉求"
        )
        self.compressor_prompt_template = self.__load_template()

    def __load_template(self) -> str:
        try:
            prompts = getattr(prompt_builder, "prompts", None) or {}
            template = prompts.get("compressor")
            if template:
                return str(template)
        except Exception as exc:
            logger.debug(f"[Compressor] 读取压缩模板失败: {exc}")
        return _FALLBACK_TEMPLATE

    def refresh_template(self) -> None:
        """模板是运行时加载的（builder 可能后加载），提供刷新入口。"""
        self.compressor_prompt_template = self.__load_template()

    def __generate_compressed_id(self, message_ids: List[str]) -> str:
        import hashlib

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        hash_input = ",".join(message_ids).encode("utf-8")
        return f"{timestamp}_{hashlib.md5(hash_input).hexdigest()[:12]}"

    async def compress_context(self, messages: Optional[List[T]] = None) -> CompressedContext:
        if not messages:
            raise ValueError("messages cannot be empty")
        valid_messages = [msg for msg in messages if msg.content and msg.content.strip()]
        if not valid_messages:
            raise ValueError("No valid messages to compress")

        sorted_messages = sorted(valid_messages, key=lambda x: x.timestamp)
        message_ids = [str(msg.id) for msg in sorted_messages]
        compressed_id = self.__generate_compressed_id(message_ids)

        compressed_result = await self.__compress_with_fallback(sorted_messages)

        if isinstance(compressed_result, dict):
            compressed_text = self.__format_structured_result(compressed_result)
            summary = compressed_result.get("summary") or self._extract_summary(compressed_text)
        else:
            compressed_text = str(compressed_result)
            summary = self._extract_summary(compressed_text)

        return CompressedContext(
            id=compressed_id,
            original_ids=message_ids,
            compressed_content=compressed_text,
            summary=summary,
            created_at=datetime.now().timestamp(),
            time_range=TimeRange(
                start=datetime.fromtimestamp(min(msg.timestamp for msg in sorted_messages)),
                end=datetime.fromtimestamp(max(msg.timestamp for msg in sorted_messages)),
            ),
            session_id=sorted_messages[0].session_id if sorted_messages else "default",
            metadata={
                "original_count": len(sorted_messages),
                "compressed_size": len(compressed_text),
                "roles": sorted({str(msg.role) for msg in sorted_messages}),
            },
        )

    def format_messages(self, messages: List[T]) -> str:
        lines: List[str] = []
        for i, msg in enumerate(messages):
            time_str = datetime.fromtimestamp(msg.timestamp).strftime("%Y-%m-%d %H:%M:%S")
            role_zh = self.__role_zh(msg.role)
            lines.append(f"[{i + 1}] [{time_str} {role_zh}]\n{msg.content}")
        return "\n\n".join(lines)

    @staticmethod
    def __role_zh(role: Any) -> str:
        try:
            return str(Role.get_zh_name(str(role)))
        except Exception:
            return str(role)

    async def __compress_with_fallback(self, messages: List[T]) -> Any:
        if self.llm_manager is not None:
            try:
                result = await asyncio.wait_for(
                    self.__llm_compress(messages),
                    timeout=self._compression_timeout,
                )
                if result:
                    return result
            except asyncio.TimeoutError:
                logger.warning("[Compressor] LLM 压缩超时，降级为规则压缩")
            except Exception as exc:
                logger.warning(f"[Compressor] LLM 压缩失败，降级为规则压缩: {exc}")
        return self.__rule_based_compress(messages)

    async def __llm_compress(self, messages: List[T]) -> Optional[dict]:
        """C104/C105：兼容不同的 LLM 接口形态。

        - LLM 实例：有 compress(prompt, system_prompt)
        - provider：只有 generate_text(messages, ...)
        - 参数名可能是 prompt 也可能是 prompt_lines（历史遗留）
        """
        formatted_dialogue = self.format_messages(messages)
        prompt = self.compressor_prompt_template.replace(
            self.dialogue_placeholder, formatted_dialogue
        )
        response = await self.__call_llm(prompt)
        if not response:
            return None

        # 抽出 JSON 部分（LLM 常带 markdown 代码块）
        text = str(response).strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start:end])
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                pass
        return None

    async def __call_llm(self, prompt: str) -> Optional[str]:
        """按能力探测调用 LLM。"""
        manager = self.llm_manager

        compress_fn = getattr(manager, "compress", None)
        if callable(compress_fn):
            # C104：优先按正确参数名调用，失败再退回位置参数
            try:
                result = compress_fn(prompt=prompt, system_prompt=self.SYSTEM_PROMPT)
            except TypeError:
                try:
                    result = compress_fn(prompt_lines=prompt, system_prompt=self.SYSTEM_PROMPT)
                except TypeError:
                    result = compress_fn(prompt, self.SYSTEM_PROMPT)
            if asyncio.iscoroutine(result):
                result = await result
            return str(result) if result else None

        # C105：provider 只有 generate_text
        generate_fn = getattr(manager, "generate_text", None)
        if callable(generate_fn):
            result = generate_fn(
                [
                    {"role": Role.SYSTEM, "content": self.SYSTEM_PROMPT},
                    {"role": Role.USER, "content": prompt},
                ]
            )
            if asyncio.iscoroutine(result):
                result = await result
            return str(result) if result else None

        logger.debug("[Compressor] llm_manager 不提供 compress/generate_text，跳过")
        return None

    # ---------- 规则降级 ----------

    def __rule_based_compress(self, messages: List[T]) -> str:
        if len(messages) <= 10:
            return self.__summarize_short_conversation(messages)
        return self.__summarize_long_conversation(messages)

    def __summarize_short_conversation(self, messages: List[T]) -> str:
        out: List[str] = []
        current_topic = None
        topic_messages: List[str] = []
        for msg in messages:
            time_str = datetime.fromtimestamp(msg.timestamp).strftime("%H:%M:%S")
            role_zh = self.__role_zh(msg.role)
            content = str(msg.content)[:150]
            first_line = content.split("\n")[0][:30]
            if current_topic != first_line:
                if topic_messages:
                    out.append(f"【{current_topic}】")
                    out.extend(topic_messages)
                current_topic = first_line
                topic_messages = []
            topic_messages.append(f"[{time_str} {role_zh}] {content}")
        if topic_messages:
            out.append(f"【{current_topic}】")
            out.extend(topic_messages)
        return "\n".join(out)

    def __summarize_long_conversation(self, messages: List[T]) -> str:
        user_msgs = [m for m in messages if str(m.role) == Role.USER]
        ai_msgs = [m for m in messages if str(m.role) == Role.ASSISTANT]
        step = max(len(messages) // 20, 1)
        key_messages = messages[::step]
        out = [
            f"# 对话摘要 ({len(messages)} 条消息)",
            f"- 用户发言: {len(user_msgs)} 次",
            f"- AI回复: {len(ai_msgs)} 次",
            "- 时间跨度: "
            + datetime.fromtimestamp(messages[0].timestamp).strftime("%H:%M")
            + " - "
            + datetime.fromtimestamp(messages[-1].timestamp).strftime("%H:%M"),
            "",
            "## 关键节点",
        ]
        for msg in key_messages:
            time_str = datetime.fromtimestamp(msg.timestamp).strftime("%H:%M:%S")
            role_zh = self.__role_zh(msg.role)
            content = str(msg.content)[:100]
            out.append(f"[{time_str} {role_zh}] {content}")
        return "\n".join(out)

    def __format_structured_result(self, result: dict) -> str:
        parts = [f"## 摘要\n{result.get('summary', '')}"]
        if result.get("key_points"):
            parts.append("\n## 关键信息")
            for point in result["key_points"]:
                if not isinstance(point, dict):
                    parts.append(f"- {point}")
                    continue
                parts.append(
                    f"- [{point.get('importance', 0)}★] "
                    f"{point.get('topic', '')}: {point.get('content', '')}"
                )
        if result.get("decisions"):
            parts.append("\n## 决策")
            for decision in result["decisions"]:
                parts.append(f"- {decision}")
        if result.get("pending_items"):
            parts.append("\n## 待办事项")
            for item in result["pending_items"]:
                parts.append(f"- [ ] {item}")
        if result.get("user_intent"):
            parts.append(f"\n## 用户意图\n{result['user_intent']}")
        return "\n".join(parts)

    def _extract_summary(self, compressed_text: str, max_length: int = 200) -> str:
        for prefix in ["## 摘要", "# 摘要", "摘要:"]:
            for line in compressed_text.splitlines():
                if line.strip().startswith(prefix):
                    return line.split(prefix)[-1].strip()[:max_length]
        for line in compressed_text.splitlines():
            text = line.strip()
            if text and not text.startswith("#"):
                return text[:max_length]
        return "对话压缩摘要"
