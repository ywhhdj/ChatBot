from __future__ import annotations
import asyncio
from datetime import datetime
import hashlib
from typing import List, Optional
from ..types.memory.context import CompressedContext, Message, TimeRange
from ..types.common import Role

class ContextCompressor:
    def __init__(self, llm_manager= None) -> None:
        self.llm_manager = llm_manager
        self.dialogue_placeholder = "${dialogue}"
        self._compression_timeout = 15.0
        from ..utils.file import read_markdown
        self.SYSTEM_PROMPT = """你是一个专业的对话压缩助手，擅长将长对话压缩为结构化摘要。核心原则：
        1. 保持信息的准确性和完整性
        2. 按时间顺序组织内容
        3. 突出关键决策和行动项
        4. 保留用户的核心诉求"
        """
        from ..config.builder import prompt_builder
        self.compressor_prompt_template = prompt_builder.prompts["compressor"]

    def __generate_compressed_id(self, message_ids: List[str]) -> str:
        """生成压缩记录的唯一ID"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        hash_input = ",".join(message_ids).encode("utf-8")
        return f"{timestamp}_{hashlib.md5(hash_input).hexdigest()[:12]}"

    async def compress_context(self, messages: Optional[List[Message]] = None) -> CompressedContext:
        """压缩对话上下文"""
        if not messages:
            raise ValueError("messages cannot be empty")
        valid_messages = [msg for msg in messages if msg.content and msg.content.strip()]
        if not valid_messages:
            raise ValueError("No valid messages to compress")
        sorted_messages = sorted(valid_messages, key=lambda x: x.timestamp)
        message_ids = [str(msg.id) for msg in sorted_messages]
        compressed_id = self.__generate_compressed_id(message_ids)
        
        # 并行执行压缩和摘要提取
        compressed_result = await self.__compress_with_fallback(sorted_messages)
        
        # 解析结构化结果
        if isinstance(compressed_result, dict):
            compressed_text = self.__format_structured_result(compressed_result)
            summary = compressed_result.get("summary", self._extract_summary(compressed_text))
        else:
            compressed_text = compressed_result
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

    def format_messages(self, messages: List[Message]) -> str:
        """格式化消息为文本"""
        lines: list[str] = []
        for i, msg in enumerate(messages):
            time_str = datetime.fromtimestamp(msg.timestamp).strftime("%Y-%m-%d %H:%M:%S")
            role_zh = Role.get_zh_name(str(msg.role))
            # 添加序号便于LLM理解对话顺序
            lines.append(f"[{i+1}] [{time_str} {role_zh}]\n{msg.content}")
        return "\n\n".join(lines)
    
    async def __compress_with_fallback(self, messages: List[Message]):
        """带降级策略的压缩"""
        if self.llm_manager is not None and self.llm_manager.is_initialized:
            try:
                # 尝试使用LLM压缩
                result = await self.__llm_compress(messages)
                if result:
                    return result
            except (asyncio.TimeoutError, Exception) as e:
                print(f"LLM compression failed: {e}, using fallback")
        return self.__rule_based_compress(messages)
    
    async def __llm_compress(self, messages: List[Message]) -> Optional[dict]:
        formatted_dialogue = self.format_messages(messages)
        prompt = self.compressor_prompt_template.replace(self.dialogue_placeholder, formatted_dialogue)
        
        try:
            response = await asyncio.wait_for(
                self.llm_manager.compress( # type: ignore
                    prompt_lines=prompt,
                    system_prompt=self.SYSTEM_PROMPT
                ),
                timeout=self._compression_timeout
            )
            # 尝试解析JSON响应
            if response:
                import json
                # 提取JSON部分
                json_start = response.find('{')
                json_end = response.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    try:
                        return json.loads(response[json_start:json_end])
                    except json.JSONDecodeError:
                        pass
            return None
        except Exception:
            return None
    
    def __rule_based_compress(self, messages: List[Message]) -> str:
        """基于规则的压缩（降级方案）"""
        if len(messages) <= 10:
            return self.__summarize_short_conversation(messages)
        else:
            return self.__summarize_long_conversation(messages)
    
    def __summarize_short_conversation(self, messages: List[Message]) -> str:
        """短对话压缩"""
        out = []
        current_topic = None
        topic_messages = []
        
        for msg in messages:
            time_str = datetime.fromtimestamp(msg.timestamp).strftime("%H:%M:%S")
            role_zh = Role.get_zh_name(str(msg.role))
            content = str(msg.content)[:150]
            
            # 检测话题变化
            first_line = content.split('\n')[0][:30]
            if current_topic != first_line:
                if topic_messages:
                    out.append(f"【{current_topic}】")
                    out.extend(topic_messages)
                current_topic = first_line
                topic_messages = []
            
            topic_messages.append(f"[{time_str} {role_zh}] {content}")
        
        # 处理最后的话题
        if topic_messages:
            out.append(f"【{current_topic}】")
            out.extend(topic_messages)
        
        return "\n".join(out)
    
    def __summarize_long_conversation(self, messages: List[Message]) -> str:
        """长对话压缩"""
        # 按角色分组统计
        user_msgs = [m for m in messages if str(m.role) == "user"]
        ai_msgs = [m for m in messages if str(m.role) == "assistant"]
        
        # 提取关键节点（每5条取一条）
        step = max(len(messages) // 20, 1)
        key_messages = messages[::step]
        
        out = [
            f"# 对话摘要 ({len(messages)} 条消息)",
            f"- 用户发言: {len(user_msgs)} 次",
            f"- AI回复: {len(ai_msgs)} 次",
            f"- 时间跨度: {datetime.fromtimestamp(messages[0].timestamp).strftime('%H:%M')} - {datetime.fromtimestamp(messages[-1].timestamp).strftime('%H:%M')}",
            "",
            "## 关键节点"
        ]
        
        for msg in key_messages:
            time_str = datetime.fromtimestamp(msg.timestamp).strftime("%H:%M:%S")
            role_zh = Role.get_zh_name(str(msg.role))
            content = str(msg.content)[:100]
            out.append(f"[{time_str} {role_zh}] {content}")
        
        return "\n".join(out)
    
    def __format_structured_result(self, result: dict) -> str:
        """将结构化结果格式化为文本"""
        parts = [f"## 摘要\n{result.get('summary', '')}"]
        if result.get('key_points'):
            parts.append("\n## 关键信息")
            for point in result['key_points']:
                parts.append(f"- [{point.get('importance', 0)}★] {point.get('topic', '')}: {point.get('content', '')}")
        if result.get('decisions'):
            parts.append("\n## 决策")
            for decision in result['decisions']:
                parts.append(f"- {decision}")
        if result.get('pending_items'):
            parts.append("\n## 待办事项")
            for item in result['pending_items']:
                parts.append(f"- [ ] {item}")
        if result.get('user_intent'):
            parts.append(f"\n## 用户意图\n{result['user_intent']}")
        return "\n".join(parts)
    
    def _extract_summary(self, compressed_text: str, max_length: int = 200) -> str:
        # 优先查找结构化摘要
        for prefix in ["## 摘要", "# 摘要", "摘要:"]:
            for line in compressed_text.splitlines():
                if line.strip().startswith(prefix):
                    text = line.split(prefix)[-1].strip()
                    return text[:max_length]
        
        # 降级：取第一行非空文本
        for line in compressed_text.splitlines():
            text = line.strip()
            if text and not text.startswith("#"):
                return text[:max_length]
        return "对话压缩摘要"
