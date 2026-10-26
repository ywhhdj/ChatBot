"""
character_system/presets.py — 角色预设模板

提供几个开箱即用的角色模板，用户也可以自定义。
"""
from __future__ import annotations
import os
from typing import List, Optional

from src_py.modules.runtime import RuntimePath

from .models import Character, CharacterAttributes, CharacterState
from ..pipeline.emotion.predictor import id_to_name
from..utils.file import yaml

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
    mood: int = 4,
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
        topics_allowed=[
            "日常",
            "现代科技",
            "古代回忆",
            "美食",
            "动画",
        ],
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
        affection=55
    )

def load_character(path: str) -> List[Character]:
    characters: List[Character] = []
    if path.endswith(".yaml"):
        data=yaml.read_yaml(path)
        for id,character_data in data.items():
            character = create_custom(
                id=id,
                name=character_data["name"],
                title=character_data["title"],
                nickname_for_user=character_data["nickname_for_user"],
                personality=character_data["personality"],
                background=character_data["background"],
                speech_style=character_data["speech_style"],
                topics_allowed=character_data["topics_allowed"],
                topics_forbidden=character_data["topics_forbidden"],
                catchphrases=character_data["catchphrases"],
                rules=character_data["rules"],
                random_words=character_data["random_words"],
                action_verbs=character_data["action_verbs"],
                emotion_adjectives=character_data["emotion_adjectives"],
                mood_modifiers=character_data["mood_modifiers"],
                affection=character_data["affection"],
                mood=character_data["mood"],
            ) 
            characters.append(character)
    return characters


def create_defaults() :
    path=str(RuntimePath.get_roles_file_path(is_defaults=True))
    return load_character(path)
    