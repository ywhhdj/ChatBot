"""意图路由：规则优先，模糊时交给轻量 LLM 判断。

修复对应清单：C13 C14 C32 C33 C34 C35 / CD3

两个"回退路径本身会崩"的坑：
  C13 `_llm_predict` 的失败分支 `RouteDecision(RouteType.MIXED, 0.3, reason=...)`
       少给两个位置参数 -> TypeError。即"LLM 判断失败"这个兜底自己会抛异常，
       把整条路由打断。
  C14 `json.loads(raw)` 不剥离 markdown 代码块。LLM 极常返回 ```json ... ```，
       直接抛错 -> 每次都走失败回退 -> 轻量判断等于没做。

以及 C32：`_quick_rule_match` / `_check_special_patterns` 是纯正则，
却用 `asyncio.to_thread` 丢进**默认线程池**（前一轮 S7 明确要避免），
线程切换开销还大于计算本身。
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Generic, Optional, TypeVar

from ..models import Role
from ..utils.file import json
from ..logger import logger
from .models import KeyWords, RouteDecision, RouteDecisionCache, RouteType
from .words import KeywordMatcher

T = TypeVar("T")

# 从 LLM 返回里抽出 JSON 对象（兼容 ```json 代码块、前后废话）
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_JSON_OBJ_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


def _extract_json(raw: str) -> Optional[Dict[str, Any]]:
    """C14：先整体解析，再剥代码块，最后正则兜底。"""
    if not raw:
        return None
    text = raw.strip()

    for candidate in (text, _strip_code_block(text)):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    match = _JSON_OBJ_RE.search(_strip_code_block(text) or text)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return None


def _strip_code_block(text: str) -> str:
    match = _JSON_BLOCK_RE.search(text)
    return match.group(1).strip() if match else ""


class LRUCache(Generic[T]):
    """C33：加锁。IntentRouter 可能被多个事件循环并发调用。"""

    def __init__(self, cache_ttl: int = 300, capacity: int = 200, cleanup_interval: int = 60):
        self.cache: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self.capacity = capacity
        self._cache_ttl = cache_ttl
        self._last_cleanup = datetime.now()
        self._cleanup_interval = cleanup_interval
        self._hit_count = 0
        self._miss_count = 0
        self._lock = threading.RLock()

    def get(self, key: str) -> Optional[T]:
        with self._lock:
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
        with self._lock:
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
        with self._lock:
            total = self._hit_count + self._miss_count
            return {
                "size": len(self.cache),
                "capacity": self.capacity,
                "hit_rate": self._hit_count / total if total else 0,
                "hits": self._hit_count,
                "misses": self._miss_count,
            }

    def clear(self) -> None:
        with self._lock:
            self.cache.clear()


class IntentRouter:
    """规则优先的路由器；置信度不足时用轻量 LLM 兜底。"""

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
        self.stats: Dict[str, Any] = {
            "total_routes": 0,
            "pure_chat": 0,
            "tool_call": 0,
            "mixed": 0,
            "ambiguous": 0,
            "cache_hits": 0,
            "avg_response_time": 0.0,
            "response_times": [],
        }
        self._stats_lock = threading.RLock()

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
        try:
            data = json.read_json(path)
            if data:
                return KeyWords(**data)
        except Exception as exc:
            logger.warning(f"[Intent] 读取 keywords.json 失败，使用空关键词: {exc}")
        return KeyWords()# type: ignore

    def _init_matchers(self) -> None:
        try:
            keywords = self.read_keywords()
            tools = keywords["tools"] if _has_key(keywords, "tools") else {}
            emotional = keywords["emotional"] if _has_key(keywords, "emotional") else {}
            self._tool_matcher.build_from_keywords(tools)
            self._emotional_matcher.build_from_keywords(
                {"emotional": emotional}, default_weight=0.75
            )
        except Exception as exc:
            logger.warning(f"[Intent] 关键词初始化失败，退化为纯规则路由: {exc}")

    async def route(
        self,
        user_input: str,
        use_llm_for_ambiguous: bool = True,
        llm_predict_func: Optional[Callable[..., Awaitable[str]]] = None,
    ) -> RouteType:
        start_time = datetime.now()
        self._bump("total_routes")

        cache_key = self._get_cache_key(user_input)
        cached = self._intent_cache.get(cache_key)
        if cached is not None:
            self._bump("cache_hits")
            self._update_response_time(start_time)
            return cached.decision.route_type

        # C32：这两个是纯 CPU 正则，直接同步调用。
        # 用 asyncio.to_thread 会占用默认线程池（前一轮 S7 明确要避免），
        # 且线程切换开销大于正则本身。
        rule_result = self._quick_rule_match(user_input)
        pattern_result = self._check_special_patterns(user_input)
        decision = self._merge_results(rule_result, pattern_result)

        if (
            decision.route_type == RouteType.MIXED
            and use_llm_for_ambiguous
            and llm_predict_func is not None
            and decision.confidence < self.config["min_confidence_for_llm"]
        ):
            decision = await self._llm_predict(user_input, llm_predict_func)

        self._bump(decision.route_type.value)
        self._intent_cache.put(cache_key, RouteDecisionCache(
            timestamp=datetime.now(),
            decision=decision,
        ))
        self._update_response_time(start_time)
        return decision.route_type

    def _bump(self, key: str, delta: int = 1) -> None:
        with self._stats_lock:
            self.stats[key] = self.stats.get(key, 0) + delta

    def _merge_results(self, rule_result: Dict[str, Any], pattern_result: Dict[str, Any]) -> RouteDecision:
        tool_confidence = max(rule_result["tool_confidence"], pattern_result["tool_confidence"])
        emotional_confidence = rule_result["emotional_confidence"]
        services = sorted(set(rule_result["detected_services"] + pattern_result["services"]))
        intents = sorted(set(rule_result["detected_intents"] + pattern_result["intents"]))

        if (
            tool_confidence >= self.config["tool_threshold"]
            and emotional_confidence < self.config["emotion_threshold"]
        ):
            return RouteDecision(RouteType.TOOL_CALL, tool_confidence, intents, services, "明确工具任务")
        if (
            emotional_confidence >= self.config["emotion_threshold"]
            and tool_confidence < self.config["mixed_threshold"]
        ):
            return RouteDecision(RouteType.PURE_CHAT, emotional_confidence, ["emotional"], services, "明确情感聊天")
        if (
            tool_confidence >= self.config["mixed_threshold"]
            and emotional_confidence >= self.config["emotion_threshold"]
        ):
            return RouteDecision(
                RouteType.MIXED,
                (tool_confidence + emotional_confidence) / 2,
                intents,
                services,
                "任务与聊天混合",
            )
        if tool_confidence >= self.config["mixed_threshold"]:
            return RouteDecision(RouteType.TOOL_CALL, tool_confidence, intents, services, "疑似明确任务")
        return RouteDecision(
            RouteType.MIXED,
            max(tool_confidence, emotional_confidence, 0.3),
            intents,
            services,
            "需要轻量判断",
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
        result: Dict[str, Any] = {"intents": [], "services": [], "tool_confidence": 0.0}
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
            raw = await llm_func([{"role": Role.USER, "content": user_input}])
            data = _extract_json(raw)
            if not data:
                raise ValueError("LLM 返回不是合法 JSON")
            route_type = RouteType(data.get("type", RouteType.MIXED.value))
            confidence = float(data.get("confidence", 0.5))
            return RouteDecision(
                route_type=route_type,
                confidence=confidence,
                detected_intents=list(data.get("intents") or data.get("detected_intents") or []),
                suggested_services=list(data.get("services") or data.get("suggested_services") or []),
                reason=str(data.get("reason", "LLM 判断")),
            )
        except Exception as exc:
            logger.warning(f"Intent LLM judge failed: {exc}")
            # C13：补齐全部位置参数。
            # 原来只给两个位置参数 -> TypeError，兜底路径自己会崩。
            return RouteDecision(
                route_type=RouteType.MIXED,
                confidence=0.3,
                detected_intents=[],
                suggested_services=[],
                reason="LLM 判断失败，回退混合模式",
            )

    def _get_cache_key(self, user_input: str) -> str:
        normalized = re.sub(r"[^\w\u4e00-\u9fff]", "", user_input.strip().lower())
        return hashlib.md5(normalized.encode("utf-8")).hexdigest()

    def _update_response_time(self, start_time: datetime) -> None:
        response_time = (datetime.now() - start_time).total_seconds()
        with self._stats_lock:
            times = self.stats["response_times"]
            times.append(response_time)
            if len(times) > 100:
                times.pop(0)
            self.stats["avg_response_time"] = sum(times) / len(times) if times else 0.0

    def get_stats(self) -> Dict[str, Any]:
        with self._stats_lock:
            total = self.stats["total_routes"]
            stats = {k: v for k, v in self.stats.items() if k != "response_times"}
        stats["cache"] = self._intent_cache.get_stats()
        stats["hit_rate"] = stats["cache_hits"] / total if total else 0
        return stats

    def clear_cache(self) -> None:
        self._intent_cache.clear()


def _has_key(obj: Any, key: str) -> bool:
    """兼容 pydantic 对象与 dict 两种 KeyWords 形态。"""
    if isinstance(obj, dict):
        return key in obj
    return hasattr(obj, key)
