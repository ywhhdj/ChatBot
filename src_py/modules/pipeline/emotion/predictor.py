"""情绪预测（LLM 文本 -> 情绪 id）。

修复对应清单：P10 / C53

P10 两个同名映射方向相反，混用必 KeyError：
    `pipeline/emotion/predictor.py` 的 `emotion_map` 是 **{名称: id}**
    `characters/presets.py`      的 `emotion_map` 是 **{id: 名称}**

    这里统一对外提供 `name_to_id()` / `id_to_name()` 两个函数，
    内部维护一份真值表，避免再有人直接下标访问。

C53 `classify()` 原实现 `return emotion_map[emotion]`，模型返回未知情绪名时
    直接 KeyError —— 情绪 id 又会被写进 `CharacterState.mood`，
    一处越界就打断整轮对话。现在未知情绪回落"平静"(4)。
"""

from __future__ import annotations

from typing import Dict, Optional

from ...runtime import RuntimePath

# 唯一真值表（名称 -> id）
EMOTION_NAME_TO_ID: Dict[str, int] = {
    "厌恶": 0,
    "哭泣": 1,
    "害怕": 2,
    "害羞": 3,
    "平静": 4,
    "心动": 5,
    "惊讶": 6,
    "慌张": 7,
    "担心": 8,
    "无奈": 9,
    "生气": 10,
    "疑惑": 11,
    "紧张": 12,
    "自信": 13,
    "认真": 14,
    "调皮": 15,
    "难为情": 16,
    "高兴": 17,
}

# 反向表（id -> 名称）
EMOTION_ID_TO_NAME: Dict[int, str] = {
    value: key for key, value in EMOTION_NAME_TO_ID.items()
}

DEFAULT_EMOTION_ID = EMOTION_NAME_TO_ID["平静"]


def name_to_id(name: str, default: int = DEFAULT_EMOTION_ID) -> int:
    """情绪名 -> id，未知回落平静。"""
    if not name:
        return default
    return EMOTION_NAME_TO_ID.get(str(name).strip(), default)


def id_to_name(emotion_id: int, default: str = "平静") -> str:
    """id -> 情绪名，越界回落平静。"""
    try:
        return EMOTION_ID_TO_NAME.get(int(emotion_id), default)
    except (TypeError, ValueError):
        return default


class LLMEmotionClassifier:
    """文本情绪分类器（模型惰性加载，加载是耗时操作）。"""

    def __init__(self, model_dir: Optional[str] = None):
        self._model_dir = model_dir or str(RuntimePath.get_models_path("emotion"))
        self._loaded = False
        from emotion_classifier import EmotionClassifier
        self.emotion_classifier = EmotionClassifier(
            model_dir=str(self._model_dir),
            tokenizer_dir=str(self._model_dir + "/tokenizer"),
            backend="onnx",
            device="cuda",
        )

    def initialize(self) -> bool:
        """加载模型。耗时操作，应由调度器线程调用，不要放在主线程。"""
        if self._loaded:
            return True
        try:
            self.emotion_classifier.ensure_loaded()
            self._loaded = True
            return True
        except Exception as exc:
            from ...logger import logger

            logger.warning(f"[Emotion] 情绪模型加载失败，将回落平静: {exc}")
            self._loaded = False
            return False

    def classify(self, text: str) -> int:
        """分类文本，返回情绪 id（越界/失败回落平静）。"""
        if not text or not text.strip():
            return DEFAULT_EMOTION_ID
        if not self._loaded and not self.initialize():
            return DEFAULT_EMOTION_ID
        try:
            result = self.emotion_classifier.predict(text) # type: ignore
            emotion = result[0][0][0]
            return name_to_id(emotion)
        except Exception as exc:
            from ...logger import logger
            logger.warning(f"[Emotion] 情绪模型调用失败，将回落平静: {exc}")
            return DEFAULT_EMOTION_ID
