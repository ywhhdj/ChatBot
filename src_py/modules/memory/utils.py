import math
from datetime import datetime
from typing import List, Union
from numpy import float32,ndarray,zeros,dot
from numpy.linalg import norm
import hashlib

def now_str() -> str:
    return datetime.now().isoformat(timespec="seconds")
def now() -> float:
    return datetime.now().timestamp()

def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value)

def time_since(last_access_time:datetime,now:datetime)->float:
    return (now-last_access_time).total_seconds()

def cosine_similarity(vec1:ndarray,vec2:ndarray)->float:
    return dot(vec1,vec2)/(norm(vec1)*norm(vec2) +1e-8)

def compute_memory_score(
        simillarity:float,
        now:datetime,
        last_access_time:datetime,
        importance:float,
        decay_rate:float=0.001,
        widths:list[float]=[0.6,0.25,0.15]
    ):
    """
    计算记忆的分数
    Args:
        simillarity (float): 记忆与查询的相似度
        last_access_time (datetime): 记忆最后一次访问时间
        importance (float): 记忆的重要性
        decay_rate (float, optional): 衰减率. Defaults to 0.001.
        widths (list[float], optional): 权重. Defaults to [0.6,0.25,0.15].
    Returns:
        float: 记忆的分数
    """
    if len(widths) <= 0 or len(widths) > 3:
        raise ValueError("widths must 1 betwwent 3")
    widthSum=0
    for width in widths:
        widthSum+=width
    if abs(widthSum - 1.0) > 1e-6:
        raise ValueError("width sum must 1")
    delta_t=time_since(last_access_time,now)
    recency_score=math.exp(-decay_rate*delta_t)
    importance_score=importance/10.0
    return (
        widths[0]*simillarity+
        widths[1]*importance_score+
        widths[2]*recency_score
    )

def text_to_list(text:Union[str,list[str]])->list[str]:
    if isinstance(text,str):
        return [text]
    return text

EMBED_DIM = 384


def embed_text(text: str, dim: int = EMBED_DIM) -> ndarray:
    """确定性 hash 嵌入（无模型依赖）。"""
    vec = zeros(dim, dtype=float32)
    if not text:
        return vec
    for token in str(text).lower().split():
        h = hashlib.md5(token.encode("utf-8")).hexdigest()
        vec[int(h[:8], 16) % dim] += 1.0
    n = norm(vec)
    if n > 0:
        vec = vec / n
    return vec


def embed_texts_sync(texts: List[str], dim: int = EMBED_DIM) -> ndarray:
    """批量版本，返回 shape (len(texts), dim) 的 float32 矩阵。"""
    from numpy import vstack

    if not texts:
        return zeros((0, dim), dtype=float32)
    return vstack([embed_text(t, dim) for t in texts]).astype(float32)
