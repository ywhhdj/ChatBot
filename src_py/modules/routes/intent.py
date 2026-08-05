from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Generic, Optional, TypeVar

from ..utils.file import read_json
from ..logger import logger
from .models import KeyWords, RouteDecision, RouteDecisionCache, RouteType
from .words import KeywordMatcher

T = TypeVar("T")


class LRUCache(Generic[T]):
    def __init__(self, cache_ttl: int = 300, capacity: int = 200, cleanup_interval: int = 60):
        self.cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.capacity = capacity
        self._cache_ttl = cache_ttl
        self._last_cleanup = datetime.now()
        self._cleanup_interval = cleanup_interval
        self._hit_count = 0
        self._miss_count = 0

    def get(self, key: str) -> Optional[T]:
        entry = self.cache.get(key)
        if not entry:
            self._miss_count += 1
            return None
        if (datetime.now() - entry["timestamp"]).total_seconds() >= self._cache_ttl:
            del self.cache[key]
            self._miss_count += 1
            return None
        self.cache.move_to_end(key)
        self._hit_count += 1
        return entry["value"]

    def put(self, key: str, value: T) -> None:
        self.cache[key] = {"timestamp": datetime.now(), "value": value}
        self.cache.move_to_end(key)
        while len(self.cache) > self.capacity:
            self.cache.popitem(last=False)
        self._periodic_cleanup()

    def _periodic_cleanup(self) -> None:
        now = datetime.now()
        if (now - self._last_cleanup).total_seconds() >= self._cleanup_interval:
            expired = [
                key for key, value in self.cache.items()
                if (now - value["timestamp"]).total_seconds() > self._cache_ttl
            ]
            for key in expired:
                del self.cache[key]
            self._last_cleanup = now

    def get_stats(self) -> Dict[str, Any]:
        total = self._hit_count + self._miss_count
        return {
            "size": len(self.cache),
            "capacity": self.capacity,
            "hit_rate": self._hit_count / total if total else 0,
            "hits": self._hit_count,
            "misses": self._miss_count,
        }


class IntentRouter:
    """Fast rule router; ambiguous requests can be judged by a lightweight LLM call."""

    def __init__(self) -> None:
        self.config = self._default_config()
        self._tool_matcher = KeywordMatcher()
        self._emotional_matcher = KeywordMatcher()
        self._init_matchers()
        self._intent_cache: LRUCache[RouteDecisionCache] = LRUCache(
            cache_ttl=self.config["cache_ttl"],
            capacity=self.config["cache_capacity"],
            cleanup_interval=self.config["cleanup_interval"],
        )
        self.stats = {
            "total_routes": 0,
            "pure_chat": 0,
            "tool_call": 0,
            "mixed": 0,
            "ambiguous": 0,
            "cache_hits": 0,
            "avg_response_time": 0.0,
            "response_times": [],
        }

    def _default_config(self) -> Dict[str, Any]:
        return {
            "cache_ttl": 600,
            "cache_capacity": 500,
            "cleanup_interval": 600,
            "tool_threshold": 0.80,
            "emotion_threshold": 0.70,
            "mixed_threshold": 0.50,
            "min_confidence_for_llm": 0.45,
        }

    def read_keywords(self) -> KeyWords:
        path = Path(__file__).with_name("keywords.json")
        return  KeyWords(**read_json(path))

    def _init_matchers(self) -> None:
        keywords = self.read_keywords()
        self._tool_matcher.build_from_keywords(keywords["tools"])
        self._emotional_matcher.build_from_keywords({"emotional": keywords["emotional"]}, default_weight=0.75)

    async def route(
        self,
        user_input: str,
        use_llm_for_ambiguous: bool = True,
        llm_predict_func: Optional[Callable[..., Awaitable[str]]] = None,
    ) -> RouteType:
        start_time = datetime.now()
        self.stats["total_routes"] += 1
        cache_key = self._get_cache_key(user_input)
        cached = self._intent_cache.get(cache_key)
        if cached:
            self.stats["cache_hits"] += 1
            self._update_response_time(start_time)
            return cached.decision.route_type

        rule_result, pattern_result = await asyncio.gather(
            asyncio.to_thread(self._quick_rule_match, user_input),
            asyncio.to_thread(self._check_special_patterns, user_input),
        )
        decision = self._merge_results(rule_result, pattern_result)
        if (
            decision.route_type == RouteType.MIXED
            and use_llm_for_ambiguous
            and llm_predict_func
            and decision.confidence < self.config["min_confidence_for_llm"]
        ):
            decision = await self._llm_predict(user_input, llm_predict_func)

        self.stats[decision.route_type.value] = self.stats.get(decision.route_type.value, 0) + 1
        self._intent_cache.put(cache_key, RouteDecisionCache(
            timestamp=datetime.now(),
            decision=decision
        ))
        self._update_response_time(start_time)
        return decision.route_type

    def _merge_results(self, rule_result: Dict[str, Any], pattern_result: Dict[str, Any]) -> RouteDecision:
        tool_confidence = max(rule_result["tool_confidence"], pattern_result["tool_confidence"])
        emotional_confidence = rule_result["emotional_confidence"]
        services = sorted(set(rule_result["detected_services"] + pattern_result["services"]))
        intents = sorted(set(rule_result["detected_intents"] + pattern_result["intents"]))

        if tool_confidence >= self.config["tool_threshold"] and emotional_confidence < self.config["emotion_threshold"]:
            return RouteDecision(
                RouteType.TOOL_CALL, 
                tool_confidence, 
                intents, 
                services, 
                "明确工具任务"
            )
        if emotional_confidence >= self.config["emotion_threshold"] and tool_confidence < self.config["mixed_threshold"]:
            return RouteDecision(
                RouteType.PURE_CHAT, 
                emotional_confidence, 
                ["emotional"], 
                services, 
                "明确情感聊天"
            )
        if tool_confidence >= self.config["mixed_threshold"] and emotional_confidence >= self.config["emotion_threshold"]:
            return RouteDecision(
                RouteType.MIXED, 
                (tool_confidence + emotional_confidence) / 2, 
                intents, 
                services, 
                "任务与聊天混合"
            )
        if tool_confidence >= self.config["mixed_threshold"]:
            return RouteDecision(
                RouteType.TOOL_CALL, 
                tool_confidence, 
                intents, 
                services, 
                "疑似明确任务"
            )
        return RouteDecision(
            RouteType.MIXED, 
            max(tool_confidence, emotional_confidence, 0.3), 
            intents, 
            services, 
            "需要轻量判断"
        )

    def _quick_rule_match(self, user_input: str) -> Dict[str, Any]:
        text = user_input.lower()
        tool_matches = self._tool_matcher.search(text)
        emotional_matches = self._emotional_matcher.search(text)
        return {
            "tool_confidence": max([weight for _, weight in tool_matches], default=0.0),
            "emotional_confidence": max([weight for _, weight in emotional_matches], default=0.0),
            "detected_services": list({name for name, _ in tool_matches}),
            "detected_intents": ["emotional"] if emotional_matches else [],
        }

    def _check_special_patterns(self, user_input: str) -> Dict[str, Any]:
        text = user_input.strip().lower()
        result = {"intents": [], "services": [], "tool_confidence": 0.0}
        command_patterns = [
            (r"^(帮我|请|麻烦|给我)?\s*(打开|搜索|访问|浏览)", "browser"),
            (r"^(帮我|请|麻烦)?\s*(播放|暂停|切歌)", "music"),
            (r"^(帮我|请|麻烦)?\s*(提醒|设置闹钟|定时)", "reminder"),
            (r"^(帮我|请|麻烦)?\s*(翻译|计算|截图|录制|切换场景)", "tool"),
            (r"^(skill|使用技能|调用技能)", "skill"),
        ]
        for pattern, service in command_patterns:
            if re.search(pattern, text):
                result["services"].append(service)
                result["intents"].append("command")
                result["tool_confidence"] = max(result["tool_confidence"], 0.9)
        return result

    async def _llm_predict(self, user_input: str, llm_func: Callable[..., Awaitable[str]]) -> RouteDecision:
        try:
            raw = await llm_func([{"role": "user", "content": user_input}])
            data = json.loads(raw)
            route_type = RouteType(data.get("type", RouteType.MIXED.value))
            return RouteDecision(
                route_type=route_type,
                confidence=float(data.get("confidence", 0.5)),
                reason=str(data.get("reason", "LLM 判断")),
            )
        except Exception as exc:
            logger.warning(f"Intent LLM judge failed: {exc}")
            return RouteDecision(RouteType.MIXED, 0.3, reason="LLM 判断失败，回退混合模式")

    def _get_cache_key(self, user_input: str) -> str:
        normalized = re.sub(r"[^\w\u4e00-\u9fff]", "", user_input.strip().lower())
        return hashlib.md5(normalized.encode("utf-8")).hexdigest()

    def _update_response_time(self, start_time: datetime) -> None:
        response_time = (datetime.now() - start_time).total_seconds()
        times = self.stats["response_times"]
        times.append(response_time)
        if len(times) > 100:
            times.pop(0)
        self.stats["avg_response_time"] = sum(times) / len(times) if times else 0.0

    def get_stats(self) -> Dict[str, Any]:
        total = self.stats["total_routes"]
        return {
            **self.stats,
            "cache": self._intent_cache.get_stats(),
            "hit_rate": self.stats["cache_hits"] / total if total else 0,
        }

    def clear_cache(self) -> None:
        self._intent_cache = LRUCache(
            cache_ttl=self.config["cache_ttl"],
            capacity=self.config["cache_capacity"],
            cleanup_interval=self.config["cleanup_interval"],
        )
