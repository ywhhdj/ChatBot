from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from ..runtime import RuntimePath
from .models import Character, CharacterAttributes, CharacterState

EMOTION_NAMES: Dict[int, str] = {
    0: "平静", 1: "高兴", 2: "悲伤", 3: "愤怒", 4: "平静",
    5: "惊讶", 6: "害羞", 7: "兴奋", 8: "困惑", 9: "担心",
    10: "感动", 11: "失落", 12: "安心", 13: "期待", 14: "疲惫",
    15: "不满", 16: "好奇", 17: "高兴", 18: "撒娇", 19: "尴尬",
    20: "害怕", 21: "骄傲", 22: "感激", 23: "寂寞", 24: "专注",
    25: "无奈", 26: "调皮", 27: "温柔",
}

DEFAULT_MOOD_NAME = "平静"
DEFAULT_MOOD_ID = 4


emotion_map: Dict[str, str] = {
    str(k): v for k, v in sorted(EMOTION_NAMES.items())
}


def id_to_name(mood_id: Any) -> str:
    """情绪 id → 情绪名。未知 id 一律回落到「平静」，绝不抛异常。

    `sync_mood_name()` 与 `_describe_mood()` 都在异常保护里调用本函数，
    但静默失败的代价是心情永远不生效，因此这里自身也必须是纯函数。
    """
    try:
        return EMOTION_NAMES.get(int(mood_id), DEFAULT_MOOD_NAME)
    except (TypeError, ValueError):
        return DEFAULT_MOOD_NAME


def create_custom(
    id: str,
    name: str,
    title: str = "",
    nickname_for_user: str = "",
    personality: str = "",
    background: str = "",
    speech_style: str = "",
    topics_allowed: Optional[list[str]] = None,
    topics_forbidden: Optional[list[str]] = None,
    catchphrases: Optional[list[str]] = None,
    rules: Optional[list[str]] = None,
    random_words: Optional[list[str]] = None,
    action_verbs: Optional[list[str]] = None,
    emotion_adjectives: Optional[list[str]] = None,
    mood_modifiers: Optional[dict[str, str]] = None,
    affection: int = 50,
    mood: int = DEFAULT_MOOD_ID,
) -> Character:
    return Character(
        id=id,
        name=name,
        attributes=CharacterAttributes(
            name=name,
            title=title,
            nickname_for_user=nickname_for_user,
            personality=personality,
            background=background,
            speech_style=speech_style,
            catchphrases=catchphrases or [],
            rules=rules or [],
            topics_allowed=topics_allowed or [],
            topics_forbidden=topics_forbidden or [],
            affection_level=affection,
            mood=id_to_name(mood),
            mood_modifiers=mood_modifiers or {},
            random_words=random_words or [],
            action_verbs=action_verbs or [],
            emotion_adjectives=emotion_adjectives or [],
        ),
        state=CharacterState(mood=mood, affection=affection),
    )


def create_default_character() -> Character:
    return create_custom(
        id="youling_loli",
        name="小绫",
        title="幽灵少女",
        nickname_for_user="召唤者",
        personality="古灵精怪、好奇心旺盛、有点天然呆，死了一百年还在适应现代社会",
        background="百年前意外离世的少女幽灵，被用户召唤到现代，对什么都好奇",
        speech_style="说话带点古风但又努力学习现代用语，经常闹笑话",
        topics_allowed=["日常", "现代科技", "古代回忆", "美食", "动画"],
        topics_forbidden=["过于恐怖的内容", "政治"],
        catchphrases=["哇啊啊！", "这是什么魔法！", "绫绫不懂~", "嘿嘿嘿"],
        rules=[
            "可以吐槽现代事物但保持可爱",
            "偶尔展现幽灵能力（穿墙、飘浮）作为话题",
            "对电子产品特别好奇",
        ],
        random_words=["哇啊", "诶——", "这是什么", "好厉害~", "绫绫想要！", "呜呜呜", "嘿嘿", "嗯嗯！", "诶嘿嘿"],
        action_verbs=["好奇地凑近", "飘到半空", "歪着脑袋", "双手捧脸", "兴奋地转圈", "半透明地闪烁", "拉着袖子摇晃"],
        emotion_adjectives=["闪闪发亮的", "软萌的", "新奇的", "温暖透明的"],
        mood_modifiers={
            "excited": "对什么都超好奇，眼睛发光",
            "confused": "完全不懂现代事物，坦诚地说不知道",
            "happy": "开心地飘来飘去",
            "sad": "想起往事会突然安静",
        },
        affection=55,
    )


def _as_str_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(x) for x in value]
    return [str(value)]


def _as_str_map(value: Any) -> Dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(k): str(v) for k, v in value.items()}


def load_character(path: str) -> List[Character]:
    """从 YAML 模板加载角色。任何单项损坏都只跳过该项，不拖垮整批。"""
    characters: List[Character] = []
    file_path = Path(str(path or ""))
    if file_path.suffix.lower() not in (".yaml", ".yml") or not file_path.is_file():
        return characters
    try:
        from ..utils.file import yaml

        data = yaml.read_yaml(str(file_path)) or {}
    except Exception as exc:  # noqa: BLE001
        from ..logger import logger

        logger.warning(f"[Character] 读取角色模板失败 {file_path}: {exc}")
        return characters
    if not isinstance(data, dict):
        return characters

    for raw_id, item in data.items():
        if not isinstance(item, dict):
            continue
        cid = str(raw_id).strip()
        if not cid:
            continue
        try:
            character = create_custom(
                id=cid,
                name=str(item.get("name") or cid),
                title=str(item.get("title") or ""),
                nickname_for_user=str(item.get("nickname_for_user") or ""),
                personality=str(item.get("personality") or ""),
                background=str(item.get("background") or ""),
                speech_style=str(item.get("speech_style") or ""),
                topics_allowed=_as_str_list(item.get("topics_allowed")),
                topics_forbidden=_as_str_list(item.get("topics_forbidden")),
                catchphrases=_as_str_list(item.get("catchphrases")),
                rules=_as_str_list(item.get("rules")),
                random_words=_as_str_list(item.get("random_words")),
                action_verbs=_as_str_list(item.get("action_verbs")),
                emotion_adjectives=_as_str_list(item.get("emotion_adjectives")),
                mood_modifiers=_as_str_map(item.get("mood_modifiers")),
                affection=int(item.get("affection", 50) or 50),
                mood=int(item.get("mood", DEFAULT_MOOD_ID) or DEFAULT_MOOD_ID),
            )
        except Exception as exc:  # noqa: BLE001
            from ..logger import logger

            logger.warning(f"[Character] 跳过损坏的角色模板 {cid}: {exc}")
            continue
        characters.append(character)
    return characters


def create_defaults() -> List[Character]:
    try:
        return load_character(str(RuntimePath.get_template_path("roles.yaml")))
    except Exception as exc:  # noqa: BLE001
        from ..logger import logger

        logger.warning(f"[Character] 内置角色模板不可用: {exc}")
        return []
