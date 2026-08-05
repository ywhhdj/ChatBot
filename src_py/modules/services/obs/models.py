from typing import TypedDict,Optional,TypedDict
from dataclasses import dataclass

from pydantic import BaseModel

class OBSEventType:
    class ObsWebsocketSERIVE:
        SERVICE_CONNECT = 0 # 服务端连接
        SERVICE_RECOGNIZED_SUCCESS = 2 # 服务端已识别
        SERVICE_EVENT_RESULT = 5 # 服务端返回事件结果
        SERVICE_EVENT_RESULTING = 7 # 服务端正在返回事件结果
        SERVICE_SERIAL_REQUEST = 9   #服务端返回串行处理结果

    class ObsWebsocketCLINETEvent:
        CLIENT_RECOGNIZED=1 # 客户端识别
        CLIENT_RECOGNIZED_RETRY = 3 # 客户端重新识别
        CLIENT_GET_EVENT = 6 #客户端请求获取事件信息
        CLIENT_SERIAL_REQUEST = 8 # 客户端发送串行处理请求

    # class OBSUIEvent(str, Enum):
    #     UI_EVENT_STUDIO_MODE_STATE_CHANGED = "StudioModeStateChanged"


    # class UIActionData:
    #     def __init__(self) -> None:
    #         self.studio_mode_state_is_open: bool = False

    # EventSubscription 位掩码 (协议 Enumerations)
    class EventSubscription:
        NONE = 0
        GENERAL = 1 << 0
        CONFIG = 1 << 1
        SCENES = 1 << 2
        INPUTS = 1 << 3
        TRANSITIONS = 1 << 4
        FILTERS = 1 << 5
        OUTPUTS = 1 << 6
        SCENE_ITEMS = 1 << 7
        MEDIA_INPUTS = 1 << 8
        VENDORS = 1 << 9
        UI = 1 << 10
        ALL = (GENERAL | CONFIG | SCENES | INPUTS | TRANSITIONS | FILTERS
            | OUTPUTS | SCENE_ITEMS | MEDIA_INPUTS | VENDORS | UI)
        INPUT_VOLUME_METERS = 1 << 16
        INPUT_ACTIVE_STATE_CHANGED = 1 << 17
        INPUT_SHOW_STATE_CHANGED = 1 << 18
        SCENE_ITEM_TRANSFORM_CHANGED = 1 << 19

    # 媒体输入动作 (ObsMediaInputAction)
    class ObsMediaInputAction:
        NONE = "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_NONE"
        PLAY = "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_PLAY"
        PAUSE = "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_PAUSE"
        STOP = "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP"
        RESTART = "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART"
        NEXT = "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_NEXT"
        PREVIOUS = "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_PREVIOUS"

    class GeneralEventType:
        VERSION="GetVersion"
        STATS="GetStats"
        HOTKEY_LIST="GetHotkeyList"

    class TransitionsEventType:
        TRANSITION_KIND_LIST="GetTransitionKindList"
        SCENE_TRANSITION_LIST="GetSceneTransitionList"
        CURRENT_SCENE_TRANSITION="GetCurrentSceneTransition"

    class SourceEventType:
        SOURCE_ACTIVE="GetSourceActive"
        SOURCE_SCREENSHOT="GetSourceScreenshot"
    
    class ConfigEventType:
        SCENE_COLLECTION_LIST="GetSceneCollectionList"
        CURRENT_SCENE_COLLECTION="GetCurrentSceneCollection"
        PROFILE_LIST="GetProfileList"
        SET_CURRENT_SCENE_COLLECTION="SetCurrentSceneCollection"
        SET_CURRENT_SCENE="SetCurrentScene"
        SET_CURRENT_PROFILE="SetCurrentProfile"
        GET_VIDEO_SETTINGS="GetVideoSettings"
        SET_VIDEO_SETTINGS="SetVideoSettings"
        GET_STREAM_SERVICE_SETTINGS="GetStreamServiceSettings"
        GET_RECORD_DIRECTORY="GetRecordDirectory"
        SET_RECORD_DIRECTORY="SetRecordDirectory"

class OBSError:
    class RequestError(Exception):
        def __init__(self, code: int, comment: Optional[str], response: Optional[dict] = None):
            self.code = code
            self.comment = comment
            self.response = response
            super().__init__(f"OBS request failed: code={code}, comment={comment}")

    class ConnectionError(Exception):
        def __init__(self, message: str):
            self.message = message
            super().__init__(f"OBS conection failed: {message}")

class OBSRequestParams(TypedDict):
    op:int
    d:dict

class OBSResponseData(BaseModel):
    status_code:int
    data:dict = {}
