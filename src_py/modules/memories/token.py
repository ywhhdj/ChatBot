"""Token 估算"""

from __future__ import annotations

import re

# CJK 统一表意文字 + 日文假名 + 韩文
_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u30ff\uac00-\ud7af]")


class TokenCalculator:
    """按中英文混合规则估算 token 数。"""

    def __init__(self, cn_ratio: float = 1.0, es_ratio: float = 0.75) -> None:
        """
        cn_ratio: 每个 CJK 字符折算的 token 数（约 1.0）
        es_ratio: 每个拉丁词折算的 token 数（约 0.75，即 1 词 ≈ 1.33 token）
        """
        # 保留旧属性名，便于外部按 token_ratio["cn"] 读取
        self.token_ratio = {"cn": cn_ratio, "es": es_ratio}
        self.cn_ratio = cn_ratio
        self.es_ratio = es_ratio

    def extract_tokens(self, text: str) -> int:
        if not text:
            return 0

        cjk_count = len(_CJK_RE.findall(text))
        # 去掉 CJK 后按空白切分，得到拉丁词数
        remaining = _CJK_RE.sub(" ", text)
        latin_words = len([w for w in remaining.split() if w])

        total = cjk_count * self.cn_ratio + latin_words / max(self.es_ratio, 1e-6)
        return max(0, int(total + 0.5))
