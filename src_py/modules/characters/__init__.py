"""
character_system/__init__.py
"""
from .models import (
    Character,
    CharacterAttributes,
    CharacterState,
    CharacterStatus,
    ContextType,
    BuiltPrompt
)
from .orchestrator import CharacterOrchestrator
from .presets import (
    create_ku_zixunshi,
    create_youling_loli,
    create_custom,
    list_presets,
    create_from_preset,
)

__all__ = [
    "Character",
    "CharacterAttributes",
    "CharacterState",
    "CharacterStatus",
    "ContextType",
    "BuiltPrompt",
    "CharacterOrchestrator",
    "create_ku_zixunshi",
    "create_youling_loli",
    "create_custom",
    "list_presets",
    "create_from_preset",
]
