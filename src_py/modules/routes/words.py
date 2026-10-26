"""关键词匹配器（意图路由的底层）。

README 的 `modules/routes/` 下有 `words.py`，但源码中缺失，而
`routes/intent.py` 在模块级 `from .words import KeywordMatcher` ——
ImportError 会沿 `intent → orchestrator → chat → websocket 控制器`
一路冒泡，最终让整个 Web 服务起不来。

接口（按 intent.py 的调用点反推）：

    m = KeywordMatcher()
    m.build_from_keywords({"browser": ["打开网页", ...]}, default_weight=0.85)
    m.search("帮我打开网页")   -> [("browser", 0.85), ...]

`search` 返回 ``[(类别名, 权重)]``，权重随命中词数递增并截断到 1.0。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence, Tuple

# 默认权重需 >= IntentRouter 的 tool_threshold(0.80)，
# 否则"单个关键词命中"永远够不到工具通道的判定线。
DEFAULT_WEIGHT = 0.85
MULTI_HIT_BONUS = 0.05


class _Entry:
    __slots__ = ("name", "words", "weight")

    def __init__(self, name: str, words: Sequence[str], weight: float) -> None:
        self.name = name
        # 去空、去重、小写归一（intent.py 传入的 text 已 lower）
        cleaned: List[str] = []
        seen = set()
        for w in words or []:
            key = str(w or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            cleaned.append(key)
        self.words = cleaned
        self.weight = float(weight)


class KeywordMatcher:
    """基于词表包含的轻量匹配器。

    关键词量级在百级，逐条 `in` 判断比维护 AC 自动机更简单也够快；
    匹配是纯 CPU 操作，不要放进事件循环 —— intent.py 已同步调用。
    """

    def __init__(self) -> None:
        self._entries: Dict[str, _Entry] = {}
        self._default_weight = DEFAULT_WEIGHT

    # ---------- 构建 ----------

    def build_from_keywords(
        self,
        keywords: Dict[str, Any],
        default_weight: float = DEFAULT_WEIGHT,
    ) -> None:
        """从 ``{类别: [词, ...]}`` 构建索引。

        容错：值可能是 list / str / None；整表为空时索引为空，
        `search` 返回空列表而不是抛异常。
        """
        self._default_weight = float(default_weight)
        self._entries.clear()
        if not isinstance(keywords, dict):
            return

        for name, words in keywords.items():
            if isinstance(words, str):
                words = [words]
            if not isinstance(words, Iterable):
                continue
            self._entries[str(name)] = _Entry(
                str(name), list(words), self._default_weight
            )

    def add(self, name: str, words: Sequence[str], weight: float = DEFAULT_WEIGHT) -> None:
        self._entries[str(name)] = _Entry(str(name), words, weight)

    # ---------- 查询 ----------

    def search(self, text: str) -> List[Tuple[str, float]]:
        """返回命中类别及权重；无命中返回空列表。"""
        if not text:
            return []
        haystack = str(text).lower()

        hits: List[Tuple[str, float]] = []
        for name, entry in self._entries.items():
            if not entry.words:
                continue
            matched = sum(1 for w in entry.words if w in haystack)
            if matched == 0:
                continue
            weight = min(1.0, entry.weight + (matched - 1) * MULTI_HIT_BONUS)
            hits.append((name, weight))

        # 权重高的排前面，便于调用方取 top1
        hits.sort(key=lambda item: item[1], reverse=True)
        return hits

    def match(self, text: str) -> bool:
        return bool(self.search(text))

    # ---------- 元信息 ----------

    def categories(self) -> List[str]:
        return list(self._entries.keys())

    def word_count(self) -> int:
        return sum(len(e.words) for e in self._entries.values())

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)
