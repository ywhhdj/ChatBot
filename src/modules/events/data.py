from dataclasses import dataclass
from typing import Any, Callable, Optional, TypedDict
from pydantic import BaseModel
from . import types

class BaseEvent(BaseModel):
    type:str
    args:Optional[tuple[Any,...]]=None
    kwargs:Optional[dict[str,Any]]=None
    callback:Optional[Callable[..., Any]]=None

    def to_dict(self):
        return {
            "type": self.type,
            "args": self.args,
            "kwargs": self.kwargs
        }

class LogEventData(BaseEvent):
    type:str=types.WebSocketEventType.GET_LOG
    data:Optional[dict]=None

class ChatEventData(BaseEvent):
    class Data:
        @dataclass
        class Chat:
            message:str
            session_id:str
            source:str
    type:str=types.WebSocketEventType.CHAT
    data:Optional[Data.Chat]=None


class QQBotEventData:
    class Data:
        @dataclass
        class C2C_MSG_CREATE:
            content:str
            user_id:str
        @dataclass
        class ON_FRIEND_ADDED:
            user_id:str
    
    # class C2C_MSG_CREATEEventData(BaseEvent):
    #     type:str=types.QQBotEventType.QQ_BOT_C2C_MSG_CREATE
    #     data:Optional[Data.C2C_MSG_CREATE]=None
    
    # class ON_FRIEND_ADDEDEventData(BaseEvent):
    #     type:str=types.QQBotEventType.QQ_BOT_ON_FRIEND_ADDED
    #     data:Optional[Data.ON_FRIEND_ADDED]=None

#情感变化事件
class MoodChangedEventData(BaseEvent):
    type:str=types.CharacterEventType.MOOD_CHANGED
    data:Optional[dict]=None