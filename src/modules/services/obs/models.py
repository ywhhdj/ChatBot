from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class OBSEventType:
    """obsws WebSocket op code 与常用请求名。"""

    class ObsWebsocketSERIVE:
        SERVICE_CONNECT = 0            # Hello
        SERVICE_RECOGNIZED_SUCCESS = 2 # Identified
        SERVICE_EVENT_RESULT = 5       # Event
        SERVICE_REQUEST_RESPONSE = 7   # RequestResponse  ← 原代码缺失

    class ObsWebsocketCLINETEvent:
        CLIENT_GET_EVENT = 6           # Request

    class EventSubscription:
        NONE = 0
        GENERAL = 1 << 0
        CONFIG = 1 << 1
        SCENES = 1 << 2
        INPUTS = 1 << 3
        TRANSITIONS = 1 << 4
        FILTERS = 1 << 5
        OUTPUTS = 1 << 6
        SCENEITEMS = 1 << 7
        MEDIAINPUTS = 1 << 8
        VENDORS = 1 << 9
        UI = 1 << 10
        ALL = (1 << 11) - 1

    class GeneralEventType:
        VERSION = "GetVersion"
        STATS = "GetStats"
        HOTKEY_LIST = "GetHotkeyList"

    class ConfigEventType:
        SCENE_COLLECTION_LIST = "GetSceneCollectionList"
        SET_CURRENT_SCENE_COLLECTION = "SetCurrentSceneCollection"
        PROFILE_LIST = "GetProfileList"
        SET_CURRENT_SCENE = "SetCurrentProfile"
        GET_VIDEO_SETTINGS = "GetVideoSettings"
        SET_VIDEO_SETTINGS = "SetVideoSettings"
        GET_STREAM_SERVICE_SETTINGS = "GetStreamServiceSettings"
        GET_RECORD_DIRECTORY = "GetRecordDirectory"
        SET_RECORD_DIRECTORY = "SetRecordDirectory"

    class SceneEventType:
        GET_SCENE_LIST = "GetSceneList"
        GET_CURRENT_PROGRAM_SCENE = "GetCurrentProgramScene"
        SET_CURRENT_PROGRAM_SCENE = "SetCurrentProgramScene"

    class RecordEventType:
        START_RECORD = "StartRecord"
        STOP_RECORD = "StopRecord"
        TOGGLE_RECORD = "ToggleRecord"
        GET_RECORD_STATUS = "GetRecordStatus"

    class StreamEventType:
        START_STREAM = "StartStream"
        STOP_STREAM = "StopStream"
        TOGGLE_STREAM = "ToggleStream"
        GET_STREAM_STATUS = "GetStreamStatus"


@dataclass
class OBSResponseData:
    """服务端下发的帧。"""
    status_code: Optional[int] = None   # op
    data: Optional[Dict[str, Any]] = field(default_factory=dict)


@dataclass
class OBSRequestParams:
    """客户端上发的请求帧。"""
    op: int = 6
    d: Dict[str, Any] = field(default_factory=dict)


class OBSError(Exception):
    """OBS 相关异常基类。"""
    class ConnectionError(Exception):
        pass

    class RequestError(Exception):
        def __init__(self, code: int, comment: Optional[str] = None,
                     result: Optional[dict] = None):
            self.code = code
            self.comment = comment
            self.result = result
            super().__init__(f"OBS 请求失败(code={code}): {comment}")
