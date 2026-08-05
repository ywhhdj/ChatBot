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

async def embed_text(text: str, dim: int = 384) -> ndarray:
    """
    Simple, deterministic hash embedding (fallback when no embedding model is configured).
    """
    vec = zeros(dim, dtype=float32)
    if not text:
        return vec
    for token in text.lower().split():
        h = hashlib.md5(token.encode("utf-8")).hexdigest()
        idx = int(h[:8], 16) % dim
        vec[idx] += 1.0
    norm_val = norm(vec)
    if norm_val > 0:
        vec /= norm_val
    return vec

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

    
