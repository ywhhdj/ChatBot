import re
from typing import Dict, List, Tuple


class KeywordMatcher:
    """高效的关键词匹配器，使用Trie树结构"""
    
    class _TrieNode:
        __slots__ = ("children", "is_end", "service", "weight")
        def __init__(self):
            self.children: Dict[str, "KeywordMatcher._TrieNode"] = {}
            self.is_end = False
            self.service = ""
            self.weight = 0.0

    def __init__(self):
        self._root = self._TrieNode()
        self._regex_patterns: List[Tuple[re.Pattern, str, float]] = []

    # ── 构建 ──────────────────────────────

    def build_from_keywords(
        self,
        keywords_dict: Dict[str, List[str]],
        default_weight: float = 0.85,
    ) -> None:
        """从 {service: [keywords]} 构建索引"""
        for service, keywords in keywords_dict.items():
            for kw in keywords:
                kw_lower = kw.lower()
                self._add_keyword(kw_lower, service, default_weight)
                self._regex_patterns.append(
                    (re.compile(re.escape(kw), re.IGNORECASE), service, default_weight)
                )

    def _add_keyword(self, keyword: str, service: str, weight: float) -> None:
        node = self._root
        for ch in keyword:
            node = node.children.setdefault(ch, self._TrieNode())
        node.is_end = True
        node.service = service
        node.weight = weight

    # ── 查询 ──────────────────────────────

    def search(self, text: str) -> List[Tuple[str, float]]:
        """
        返回 [(service, weight), ...]
        优先精确匹配，无结果时退到正则。
        """
        exact = self._search_exact(text.lower())
        if exact:
            return exact
        return self._search_regex(text)

    def _search_exact(self, text: str) -> List[Tuple[str, float]]:
        results: List[Tuple[str, float]] = []
        for i in range(len(text)):
            node = self._root
            for j in range(i, len(text)):
                node = node.children.get(text[j])
                if node is None:
                    break
                if node.is_end:
                    results.append((node.service, node.weight))
        return results

    def _search_regex(self, text: str) -> List[Tuple[str, float]]:
        return [
            (svc, w) for pat, svc, w in self._regex_patterns if pat.search(text)
        ]