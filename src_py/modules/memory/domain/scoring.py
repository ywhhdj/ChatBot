"""多路召回的融合与词法打分。

依据 `docs/MemoryDesign.md` §5 与 `OptimizationPlan.md` B2-01~B2-03。

设计取舍
────────
* **RRF 优先于加权分数相加**（MemoryDesign §5）：各路分数的量纲不同
  （BM25 是 0~∞，余弦是 -1~1，recency 是 0~1），直接相加等于让分数
  最大的那路独裁。RRF 只看**名次**，天然无量纲。
* **先过滤 scope，再召回**（SecurityAndAuditDesign §7）：
  绝不"全局 top-K 之后才按 session 过滤"。本模块的输入已经是
  scope 内候选，融合层不再做权限判断。
* **中文不只靠空格分词**（B2-03）：`cjk_ngrams()` 对 CJK 字符取
  单字 + bigram，拉丁词按空白/标点切分。这是**确定性**实现，
  中日英三语可复现，不依赖外部 tokenizer。

这些计算是典型的"批量、纯数值、每轮都跑"的重计算，
已同步下沉到 Rust `native/src/memory.rs`；本文件保留纯 Python
实现作为**回退与属性基准**（两者结果必须一致，由
`compute/kernel.check_constants()` 与回归集保证）。
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

#: RRF 的 k。文档给的起点值，须由 M1-06 评估集校准。
RRF_K = 60.0

#: 各路默认权重。同样是起点值，不是已验证最优。
DEFAULT_CHANNEL_WEIGHTS: Dict[str, float] = {
    "exact": 1.0,
    "lexical": 1.0,
    "dense": 1.0,
    "recency": 0.5,
    "confidence": 0.5,
}

_WORD_RE = re.compile(r"[A-Za-z0-9_]+")

def cjk_ngrams(text: str, *, max_n: int = 2) -> List[str]:
    """CJK 友好的确定性分词。

    * 汉字/假名/谚文：单字 + 相邻 bigram（中文没有空格，bigram 是
      最低成本且可复现的近似）；
    * 拉丁数字串：整体小写保留；
    * 其余标点空白一律丢弃。

    返回**列表**（保留重复，用于 TF），不是集合。
    """
    if not text:
        return []
    normalized = unicodedata.normalize("NFKC", str(text)).lower()
    out: List[str] = []

    # 先切出拉丁/数字词
    for match in _WORD_RE.finditer(normalized):
        out.append(match.group(0))

    # 再按连续 CJK 段取 n-gram
    for segment in re.findall(
        r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]+",
        normalized,
    ):
        chars = list(segment)
        out.extend(chars)
        for n in range(2, min(max_n, len(chars)) + 1):
            for i in range(len(chars) - n + 1):
                out.append("".join(chars[i:i + n]))
    return out


def _tf(tokens: Iterable[str]) -> Dict[str, float]:
    tf: Dict[str, float] = {}
    for token in tokens:
        tf[token] = tf.get(token, 0.0) + 1.0
    return tf


def lexical_score(query: str, document: str) -> float:
    """词法相关性：TF 余弦（0~1）。

    用余弦而非 BM25 原始分，是为了让输出天然归一化、可直接进 RRF
    名次；BM25 需要全语料 IDF，在增量写入场景下还得维护全局统计，
    对当前规模不划算。B2-02 的离线对照会验证这个取舍。
    """
    q = _tf(cjk_ngrams(query))
    d = _tf(cjk_ngrams(document))
    if not q or not d:
        return 0.0
    dot = 0.0
    for token, qv in q.items():
        dv = d.get(token)
        if dv:
            dot += qv * dv
    nq = math.sqrt(sum(v * v for v in q.values()))
    nd = math.sqrt(sum(v * v for v in d.values()))
    if nq <= 0 or nd <= 0:
        return 0.0
    return min(1.0, dot / (nq * nd))


def recency_score(created_at: float, now: float, *, half_life_days: float = 30.0) -> float:
    """指数衰减的近因信号（0~1）。半衰期默认 30 天。"""
    if half_life_days <= 0:
        return 1.0
    delta_days = max(0.0, float(now) - float(created_at)) / 86400.0
    return 0.5 ** (delta_days / half_life_days)


def rrf_fuse(
    rank_lists: Sequence[Sequence[Any]],
    *,
    weights: Optional[Mapping[str, float]] = None,
    k: float = RRF_K,
) -> List[Tuple[Any, float]]:
    """Reciprocal Rank Fusion。

    `rank_lists` 是若干路**已按相关性降序**的 id 列表。
    返回 `[(id, score)]`，按分数降序。

    为什么不用 dict 累加就直接返回：同名 id 可能在不同路出现，
    必须合并；重复出现在同一路只按第一次（最高名次）计。

    `weights` 的 key 是 channel 名，按 `rank_lists` 的位置对应
    `sorted(weights)` 不稳定，因此这里用调用方传入的**显式通道列表**
    （见 `fuse_channels`）。本函数保持位置语义，避免隐式映射。
    """
    k = float(k) if math.isfinite(k) and k >= 0 else RRF_K
    scores: Dict[Any, float] = {}
    for channel_index, ranked in enumerate(rank_lists):
        w = 1.0
        if weights is not None:
            # 位置权重由调用方通过 fuse_channels 转成同序列表后传入
            w = float(list(weights.values())[channel_index]) if channel_index < len(weights) else 1.0
        seen = set()
        for rank, doc_id in enumerate(ranked or []):
            if doc_id in seen:
                continue
            seen.add(doc_id)
            scores[doc_id] = scores.get(doc_id, 0.0) + w / (k + rank + 1)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)


def fuse_channels(
    channels: Mapping[str, Sequence[Any]],
    *,
    weights: Optional[Mapping[str, float]] = None,
    k: float = RRF_K,
) -> List[Tuple[Any, float]]:
    """按**显式通道名**做 RRF。推荐入口。

    `weights` 缺省用 `DEFAULT_CHANNEL_WEIGHTS`；未登记的通道权重 1.0。
    单路失败（空列表）自然退化，不需要特殊分支 —— 这正是 RRF
    比加权求和稳的地方。
    """
    weight_map = dict(DEFAULT_CHANNEL_WEIGHTS)
    if weights:
        weight_map.update({str(key): float(value) for key, value in weights.items()})

    names = list(channels.keys())
    effective = {name: float(weight_map.get(name, 1.0)) for name in names}
    # 传一个与 rank_lists 同序的权重 dict（dict 保序）
    return rrf_fuse(
        [channels[name] for name in names],
        weights=effective,
        k=k,
    )


def normalize_scores(values: Sequence[float]) -> List[float]:
    """min-max 归一化到 [0,1]。全相等时返回全 0（不制造假差异）。"""
    if not values:
        return []
    finite = [float(v) if math.isfinite(v) else 0.0 for v in values]
    lo, hi = min(finite), max(finite)
    span = hi - lo
    if span <= 0:
        return [0.0 for _ in finite]
    return [(v - lo) / span for v in finite]
