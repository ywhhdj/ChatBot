import asyncio
import asyncio
import base64
from json import loads,dumps,JSONDecodeError
from typing import Any, Dict, Optional, Union
import hashlib
from typing import Dict, Optional

from ...manager.service.decorator import Service
from ..config import ObsConfig
from .. import base
from ...logger import logger
from ...utils import util
from . import models
from ...events import on_event_class,types as eventType
from .. import ServiceId

@on_event_class([
    (eventType.ObsEventType.OBS_CONNECT, "start"),
    (eventType.ObsEventType.OBS_DISCONNECT, "stop"),
    (eventType.ObsEventType.OBS_START_RECORD, "on_asr_audio_chunk"),
    (eventType.ObsEventType.OBS_STOP_RECORD, "on_asr_final_audio")
])
@Service(id=ServiceId.OBS)
class OBSClient(base._BaseService):
    """
        References:
            <a href="https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md">OBS WebSocket Protocol</a>

        Parameters:
            ip: OBS服务器IP地址
            obs_password: OBS服务器密码
            port: OBS服务器端口号
            subprotocol: OBS服务器子协议
            timeout: 连接超时时间
    """
    name="OBS"
    description="用于控制OBS Studio录制等服务"
    
    def __init__(self, ip: str,obs_password: str ,port: int = 4455, timeout: int = 10):
        super().__init__()
        self.config = ObsConfig(
            enabled=True,
            ip=ip,
            password=obs_password,
            port=port
        )
        self.timeout = timeout
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._event_callbacks: Dict[str, list] = {}  # eventType -> [callbacks]
        self._negotiated_rpc_version: Optional[int] = None
        self.__runing: bool = False
        self.set_status()
        from websockets import ClientConnection
        self.__ws: Optional[ClientConnection] = None
    
    def set_status(self):
        if self.__runing:
            self.status= base.ServiceState.RUNNING
        else:
            self.status= base.ServiceState.STOPPED

    async def _send(self, request: dict) -> None:
        """发送请求到OBS服务器

        :param request: 要发送的请求数据
        """
        if self.__ws is not None:
            logger.info(f"[OBS] Sending request: {request}")
            await self.__ws.send(dumps(request))
        else:
            raise ConnectionError("OBS客户端未连接")

    def __build_identify(self, d: dict, auth_string: Optional[str] = None) -> dict:
        rpc_version = d.get("rpcVersion", 1)
        payload: dict = {
            "rpcVersion": rpc_version,
            "eventSubscriptions": models.OBSEventType.EventSubscription.ALL,
        }
        if auth_string is not None:
            payload["authentication"] = auth_string
        return {"op": 1, "d": payload}

    async def start(self) -> None:
        self.__runing = True
        asyncio.create_task(self.connect())
        self.set_status()
    
    def get_tools(self):
        return [

        ]

    async def connect(self) -> None:
        if self.__ws is not None:
            return
        try:
            from websockets.exceptions import ConnectionClosed
            from websockets.typing import Subprotocol
            from websockets import connect
            ws_url=f"ws://{self.config.ip}:{self.config.port}"
            while self.__runing:
                async with connect(
                    ws_url,
                    subprotocols=[Subprotocol("obswebsocket.json")],
                    open_timeout=self.timeout,
                ) as ws:
                    self.__ws = ws
                    async for msg in ws:
                        try:
                            msg = loads(msg)
                            logger.info(f"[OBS] Received message: {msg}")
                            await self.__handle_event(models.OBSResponseData(
                                status_code=msg.get("op"),
                                data=msg.get("d")
                            ))
                        except JSONDecodeError:
                            pass
        except ConnectionRefusedError as e:
            logger.error("Are you sure you have started the OBS WebSocket server?")
            raise models.OBSError.ConnectionError("OBS WebSocket 连接失败"+str(e))
        except ConnectionClosed as e:
            logger.warning("Connection closed.")
            raise models.OBSError.ConnectionError("OBS WebSocket 连接已关闭+"+str(e))
        except Exception as e:
            logger.exception("OBS WebSocket 连接异常",exc_info=True)
            raise e
        finally:
            await self.stop()

    async def stop(self) -> None:
        self.__runing = False
        if self.__ws is not None and hasattr(self.__ws, "closed"):
            await self.__ws.close()
        self.set_status()

    async def __handle_event(self, response: models.OBSResponseData) -> None:
        if response.status_code == models.OBSEventType.ObsWebsocketSERIVE.SERVICE_CONNECT:  # 0 Hello
            await self.__auth(response)
        elif response.status_code == models.OBSEventType.ObsWebsocketSERIVE.SERVICE_RECOGNIZED_SUCCESS:  # 2 Identified
            self._negotiated_rpc_version = response.data.get("negotiatedRpcVersion")
        elif response.status_code == models.OBSEventType.ObsWebsocketSERIVE.SERVICE_EVENT_RESULT:  # 5 Event
            event_type = response.data.get("eventType")
            event_data = response.data.get("eventData") or {}
            if event_type and event_type in self._event_callbacks:
                for callback in self._event_callbacks[event_type]:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(event_data)
                        else:
                            callback(event_data)
                    except Exception:
                        pass
        elif response.status_code == models.OBSEventType.ObsWebsocketSERIVE.SERVICE_EVENT_RESULT:  # 7 RequestResponse
            request_id = response.data.get("requestId")
            if request_id and request_id in self._pending_requests:
                fut = self._pending_requests.pop(request_id)
                if not fut.done():
                    fut.set_result({
                        "requestStatus": response.data.get("requestStatus"),
                        "responseData": response.data.get("responseData"),
                    })

    @property
    def is_connected(self) -> bool:
        return self.__ws is not None and not hasattr(self.__ws, "closed")

    async def request(
        self,
        request_type: str,
        request_data: Optional[dict] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """
        发送请求并等待响应，返回 responseData；失败时抛出 OBSRequestError。
        """
        request_id = util.id_generator()
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending_requests[request_id] = fut
        req= models.OBSRequestParams(
            op=models.OBSEventType.ObsWebsocketCLINETEvent.CLIENT_GET_EVENT,
            d={
                "requestType": request_type,
                "requestId": request_id,
                "requestData": request_data or {},
            }
        )
        await self._send(req.__dict__)
        try:
            result = await asyncio.wait_for(fut, timeout=timeout or self.timeout)
        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            raise
        status = result.get("requestStatus") or {}
        if not status.get("result", False):
            raise models.OBSError.RequestError(
                status.get("code", -1),
                status.get("comment"),
                result,
            )
        return result.get("responseData") or {}

    async def __auth(self, response: models.OBSResponseData) -> None:
        auth_obj = response.data.get("authentication")
        if not auth_obj:
            await self._send(self.__build_identify(response.data))
            return
        challenge: str = auth_obj.get("challenge", "")
        salt: str = auth_obj.get("salt", "")
        if not self.config:
            return
        sha256_secret = self.__generate_base64_secret(self.config.password + salt)
        my_auth = self.__generate_base64_secret(sha256_secret + challenge)
        await self._send(self.__build_identify(response.data, my_auth))

    def __generate_base64_secret(self, secret: str) -> str:
        sha256_hash = hashlib.sha256(secret.encode()).digest()
        return base64.b64encode(sha256_hash).decode("utf-8")

    # ---------- General ----------
    async def get_version(self) -> dict:
        return await self.request(models.OBSEventType.GeneralEventType.VERSION)

    async def get_stats(self) -> dict:
        return await self.request(models.OBSEventType.GeneralEventType.STATS)

    async def get_hotkey_list(self) -> dict:
        return await self.request(models.OBSEventType.GeneralEventType.HOTKEY_LIST)

    # ---------- Config ----------
    async def get_scene_collection_list(self) -> dict:
        return await self.request(models.OBSEventType.ConfigEventType.SCENE_COLLECTION_LIST)

    async def set_current_scene_collection(self, scene_collection_name: str) -> None:
        await self.request(models.OBSEventType.ConfigEventType.SET_CURRENT_SCENE_COLLECTION, {"sceneCollectionName": scene_collection_name})

    async def get_profile_list(self) -> dict:
        return await self.request(models.OBSEventType.ConfigEventType.PROFILE_LIST)

    async def set_current_profile(self, profile_name: str) -> None:
        await self.request(models.OBSEventType.ConfigEventType.SET_CURRENT_SCENE, {"profileName": profile_name})

    async def get_video_settings(self) -> dict:
        return await self.request(models.OBSEventType.ConfigEventType.GET_VIDEO_SETTINGS)

    async def set_video_settings(self, **kwargs: Any) -> None:
        await self.request(models.OBSEventType.ConfigEventType.SET_VIDEO_SETTINGS, kwargs)

    async def get_stream_service_settings(self) -> dict:
        return await self.request(models.OBSEventType.ConfigEventType.GET_STREAM_SERVICE_SETTINGS)

    async def get_record_directory(self) -> dict:
        return await self.request(models.OBSEventType.ConfigEventType.GET_RECORD_DIRECTORY)

    async def set_record_directory(self, record_directory: str) -> None:
        await self.request(models.OBSEventType.ConfigEventType.SET_RECORD_DIRECTORY, {"recordDirectory": record_directory})

    # ---------- Scenes ----------
    async def get_scene_list(self) -> dict:
        return await self.request("GetSceneList")

    async def get_group_list(self) -> dict:
        return await self.request("GetGroupList")

    async def get_current_program_scene(self) -> dict:
        return await self.request("GetCurrentProgramScene")

    async def set_current_program_scene(self, scene_name: Optional[str] = None, scene_uuid: Optional[str] = None) -> None:
        data: dict = {}
        if scene_name is not None:
            data["sceneName"] = scene_name
        if scene_uuid is not None:
            data["sceneUuid"] = scene_uuid
        await self.request("SetCurrentProgramScene", data)

    async def get_current_preview_scene(self) -> dict:
        return await self.request("GetCurrentPreviewScene")

    async def set_current_preview_scene(self, scene_name: Optional[str] = None, scene_uuid: Optional[str] = None) -> None:
        data: dict = {}
        if scene_name is not None:
            data["sceneName"] = scene_name
        if scene_uuid is not None:
            data["sceneUuid"] = scene_uuid
        await self.request("SetCurrentPreviewScene", data)

    async def create_scene(self, scene_name: str) -> dict:
        return await self.request("CreateScene", {"sceneName": scene_name})

    async def remove_scene(self, scene_name: Optional[str] = None, scene_uuid: Optional[str] = None) -> None:
        data: dict = {}
        if scene_name is not None:
            data["sceneName"] = scene_name
        if scene_uuid is not None:
            data["sceneUuid"] = scene_uuid
        await self.request("RemoveScene", data)

    async def set_scene_name(
        self,
        new_scene_name: str,
        scene_name: Optional[str] = None,
        scene_uuid: Optional[str] = None,
    ) -> None:
        data: dict = {"newSceneName": new_scene_name}
        if scene_name is not None:
            data["sceneName"] = scene_name
        if scene_uuid is not None:
            data["sceneUuid"] = scene_uuid
        await self.request("SetSceneName", data)

    async def get_scene_scene_transition_override(
        self,
        scene_name: Optional[str] = None,
        scene_uuid: Optional[str] = None,
    ) -> dict:
        data: dict = {}
        if scene_name is not None:
            data["sceneName"] = scene_name
        if scene_uuid is not None:
            data["sceneUuid"] = scene_uuid
        return await self.request("GetSceneSceneTransitionOverride", data)

    async def set_scene_scene_transition_override(
        self,
        scene_name: Optional[str] = None,
        scene_uuid: Optional[str] = None,
        transition_name: Optional[str] = None,
        transition_duration: Optional[int] = None,
    ) -> None:
        data: dict = {}
        if scene_name is not None:
            data["sceneName"] = scene_name
        if scene_uuid is not None:
            data["sceneUuid"] = scene_uuid
        if transition_name is not None:
            data["transitionName"] = transition_name
        if transition_duration is not None:
            data["transitionDuration"] = transition_duration
        await self.request("SetSceneSceneTransitionOverride", data)

    # ---------- Inputs ----------
    async def get_input_list(self, input_kind: Optional[str] = None) -> dict:
        data = {}
        if input_kind is not None:
            data["inputKind"] = input_kind
        return await self.request("GetInputList", data if data else None)

    async def get_input_kind_list(self, unversioned: bool = False) -> dict:
        return await self.request("GetInputKindList", {"unversioned": unversioned})

    async def get_special_inputs(self) -> dict:
        return await self.request("GetSpecialInputs")

    async def create_input(
        self,
        input_name: str,
        input_kind: str,
        scene_name: Optional[str] = None,
        scene_uuid: Optional[str] = None,
        input_settings: Optional[dict] = None,
        scene_item_enabled: bool = True,
    ) -> dict:
        data: dict = {"inputName": input_name, "inputKind": input_kind, "sceneItemEnabled": scene_item_enabled}
        if scene_name is not None:
            data["sceneName"] = scene_name
        if scene_uuid is not None:
            data["sceneUuid"] = scene_uuid
        if input_settings is not None:
            data["inputSettings"] = input_settings
        return await self.request("CreateInput", data)

    async def remove_input(self, input_name: Optional[str] = None, input_uuid: Optional[str] = None) -> None:
        data: dict = {}
        if input_name is not None:
            data["inputName"] = input_name
        if input_uuid is not None:
            data["inputUuid"] = input_uuid
        await self.request("RemoveInput", data)

    async def set_input_name(
        self,
        new_input_name: str,
        input_name: Optional[str] = None,
        input_uuid: Optional[str] = None,
    ) -> None:
        data: dict = {"newInputName": new_input_name}
        if input_name is not None:
            data["inputName"] = input_name
        if input_uuid is not None:
            data["inputUuid"] = input_uuid
        await self.request("SetInputName", data)

    async def get_input_default_settings(self, input_kind: str) -> dict:
        return await self.request("GetInputDefaultSettings", {"inputKind": input_kind})

    async def get_input_settings(
        self,
        input_name: Optional[str] = None,
        input_uuid: Optional[str] = None,
    ) -> dict:
        data: dict = {}
        if input_name is not None:
            data["inputName"] = input_name
        if input_uuid is not None:
            data["inputUuid"] = input_uuid
        return await self.request("GetInputSettings", data if data else None)

    async def set_input_settings(
        self,
        input_settings: dict,
        input_name: Optional[str] = None,
        input_uuid: Optional[str] = None,
        overlay: bool = True,
    ) -> None:
        data: dict = {"inputSettings": input_settings, "overlay": overlay}
        if input_name is not None:
            data["inputName"] = input_name
        if input_uuid is not None:
            data["inputUuid"] = input_uuid
        await self.request("SetInputSettings", data)

    async def get_input_mute(
        self,
        input_name: Optional[str] = None,
        input_uuid: Optional[str] = None,
    ) -> dict:
        data: dict = {}
        if input_name is not None:
            data["inputName"] = input_name
        if input_uuid is not None:
            data["inputUuid"] = input_uuid
        return await self.request("GetInputMute", data if data else None)

    async def set_input_mute(
        self,
        input_muted: bool,
        input_name: Optional[str] = None,
        input_uuid: Optional[str] = None,
    ) -> None:
        data: dict = {"inputMuted": input_muted}
        if input_name is not None:
            data["inputName"] = input_name
        if input_uuid is not None:
            data["inputUuid"] = input_uuid
        await self.request("SetInputMute", data)

    async def toggle_input_mute(
        self,
        input_name: Optional[str] = None,
        input_uuid: Optional[str] = None,
    ) -> dict:
        data: dict = {}
        if input_name is not None:
            data["inputName"] = input_name
        if input_uuid is not None:
            data["inputUuid"] = input_uuid
        return await self.request("ToggleInputMute", data if data else None)

    async def get_input_volume(
        self,
        input_name: Optional[str] = None,
        input_uuid: Optional[str] = None,
    ) -> dict:
        data: dict = {}
        if input_name is not None:
            data["inputName"] = input_name
        if input_uuid is not None:
            data["inputUuid"] = input_uuid
        return await self.request("GetInputVolume", data if data else None)

    async def set_input_volume(
        self,
        input_name: Optional[str] = None,
        input_uuid: Optional[str] = None,
        input_volume_mul: Optional[float] = None,
        input_volume_db: Optional[float] = None,
    ) -> None:
        data: dict = {}
        if input_name is not None:
            data["inputName"] = input_name
        if input_uuid is not None:
            data["inputUuid"] = input_uuid
        if input_volume_mul is not None:
            data["inputVolumeMul"] = input_volume_mul
        if input_volume_db is not None:
            data["inputVolumeDb"] = input_volume_db
        await self.request("SetInputVolume", data)

    async def get_input_audio_balance(
        self,
        input_name: Optional[str] = None,
        input_uuid: Optional[str] = None,
    ) -> dict:
        data: dict = {}
        if input_name is not None:
            data["inputName"] = input_name
        if input_uuid is not None:
            data["inputUuid"] = input_uuid
        return await self.request("GetInputAudioBalance", data if data else None)

    async def set_input_audio_balance(
        self,
        input_audio_balance: float,
        input_name: Optional[str] = None,
        input_uuid: Optional[str] = None,
    ) -> None:
        data: dict = {"inputAudioBalance": input_audio_balance}
        if input_name is not None:
            data["inputName"] = input_name
        if input_uuid is not None:
            data["inputUuid"] = input_uuid
        await self.request("SetInputAudioBalance", data)

    # ---------- Transitions ----------
    async def get_transition_kind_list(self) -> dict:
        return await self.request("GetTransitionKindList")

    async def get_scene_transition_list(self) -> dict:
        return await self.request("GetSceneTransitionList")

    async def get_current_scene_transition(self) -> dict:
        return await self.request("GetCurrentSceneTransition")

    async def set_current_scene_transition(
        self,
        transition_name: Optional[str] = None,
        transition_uuid: Optional[str] = None,
    ) -> None:
        data: dict = {}
        if transition_name is not None:
            data["transitionName"] = transition_name
        if transition_uuid is not None:
            data["transitionUuid"] = transition_uuid
        await self.request("SetCurrentSceneTransition", data if data else None)

    async def set_current_scene_transition_duration(self, transition_duration: int) -> None:
        await self.request("SetCurrentSceneTransitionDuration", {"transitionDuration": transition_duration})

    async def set_current_scene_transition_settings(
        self,
        transition_settings: dict,
        transition_name: Optional[str] = None,
        transition_uuid: Optional[str] = None,
    ) -> None:
        data: dict = {"transitionSettings": transition_settings}
        if transition_name is not None:
            data["transitionName"] = transition_name
        if transition_uuid is not None:
            data["transitionUuid"] = transition_uuid
        await self.request("SetCurrentSceneTransitionSettings", data)

    async def trigger_studio_mode_transition(self) -> None:
        await self.request("TriggerStudioModeTransition")

    async def set_tbar_position(self, position: float, release: bool = False) -> None:
        await self.request("SetTBarPosition", {"position": position, "release": release})

    # ---------- Filters ----------
    async def get_source_filter_kind_list(self) -> dict:
        return await self.request("GetSourceFilterKindList")

    async def get_source_filter_list(self, source_name: Optional[str] = None, source_uuid: Optional[str] = None) -> dict:
        data: dict = {}
        if source_name is not None:
            data["sourceName"] = source_name
        if source_uuid is not None:
            data["sourceUuid"] = source_uuid
        return await self.request("GetSourceFilterList", data if data else None)

    async def create_source_filter(
        self,
        source_name: str,
        filter_name: str,
        filter_kind: str,
        filter_settings: Optional[dict] = None,
        source_uuid: Optional[str] = None,
    ) -> dict:
        data: dict = {"sourceName": source_name, "filterName": filter_name, "filterKind": filter_kind}
        if filter_settings is not None:
            data["filterSettings"] = filter_settings
        if source_uuid is not None:
            data["sourceUuid"] = source_uuid
        return await self.request("CreateSourceFilter", data)

    async def remove_source_filter(self, source_name: str, filter_name: str) -> None:
        await self.request("RemoveSourceFilter", {"sourceName": source_name, "filterName": filter_name})

    async def set_source_filter_name(
        self,
        source_name: str,
        old_filter_name: str,
        new_filter_name: str,
    ) -> None:
        await self.request(
            "SetSourceFilterName",
            {"sourceName": source_name, "oldFilterName": old_filter_name, "filterName": new_filter_name},
        )

    async def get_source_filter(
        self,
        source_name: str,
        filter_name: str,
        source_uuid: Optional[str] = None,
    ) -> dict:
        data: dict = {"sourceName": source_name, "filterName": filter_name}
        if source_uuid is not None:
            data["sourceUuid"] = source_uuid
        return await self.request("GetSourceFilter", data)

    async def set_source_filter_index(
        self,
        source_name: str,
        filter_name: str,
        filter_index: int,
        source_uuid: Optional[str] = None,
    ) -> None:
        data: dict = {"sourceName": source_name, "filterName": filter_name, "filterIndex": filter_index}
        if source_uuid is not None:
            data["sourceUuid"] = source_uuid
        await self.request("SetSourceFilterIndex", data)

    async def set_source_filter_settings(
        self,
        source_name: str,
        filter_name: str,
        filter_settings: dict,
        source_uuid: Optional[str] = None,
    ) -> None:
        data: dict = {"sourceName": source_name, "filterName": filter_name, "filterSettings": filter_settings}
        if source_uuid is not None:
            data["sourceUuid"] = source_uuid
        await self.request("SetSourceFilterSettings", data)

    async def set_source_filter_enabled(
        self,
        source_name: str,
        filter_name: str,
        filter_enabled: bool,
        source_uuid: Optional[str] = None,
    ) -> None:
        data: dict = {"sourceName": source_name, "filterName": filter_name, "filterEnabled": filter_enabled}
        if source_uuid is not None:
            data["sourceUuid"] = source_uuid
        await self.request("SetSourceFilterEnabled", data)

    # ---------- Scene Items ----------
    async def get_scene_item_list(
        self,
        scene_name: Optional[str] = None,
        scene_uuid: Optional[str] = None,
    ) -> dict:
        data: dict = {}
        if scene_name is not None:
            data["sceneName"] = scene_name
        if scene_uuid is not None:
            data["sceneUuid"] = scene_uuid
        return await self.request("GetSceneItemList", data if data else None)

    async def get_group_scene_item_list(
        self,
        scene_name: str,
        scene_uuid: Optional[str] = None,
    ) -> dict:
        data: dict = {"sceneName": scene_name}
        if scene_uuid is not None:
            data["sceneUuid"] = scene_uuid
        return await self.request("GetGroupSceneItemList", data)

    async def get_scene_item_id(
        self,
        scene_name: str,
        scene_item_id: int,
        scene_uuid: Optional[str] = None,
    ) -> dict:
        data: dict = {"sceneName": scene_name, "sceneItemId": scene_item_id}
        if scene_uuid is not None:
            data["sceneUuid"] = scene_uuid
        return await self.request("GetSceneItemId", data)

    async def create_scene_item(
        self,
        scene_name: str,
        source_name: Optional[str] = None,
        source_uuid: Optional[str] = None,
        scene_item_enabled: bool = True,
        scene_uuid: Optional[str] = None,
    ) -> dict:
        data: dict = {"sceneName": scene_name, "sceneItemEnabled": scene_item_enabled}
        if source_name is not None:
            data["sourceName"] = source_name
        if source_uuid is not None:
            data["sourceUuid"] = source_uuid
        if scene_uuid is not None:
            data["sceneUuid"] = scene_uuid
        return await self.request("CreateSceneItem", data)

    async def remove_scene_item(
        self,
        scene_name: str,
        scene_item_id: int,
        scene_uuid: Optional[str] = None,
    ) -> None:
        data: dict = {"sceneName": scene_name, "sceneItemId": scene_item_id}
        if scene_uuid is not None:
            data["sceneUuid"] = scene_uuid
        await self.request("RemoveSceneItem", data)

    async def get_scene_item_transform(
        self,
        scene_name: str,
        scene_item_id: int,
        scene_uuid: Optional[str] = None,
    ) -> dict:
        data: dict = {"sceneName": scene_name, "sceneItemId": scene_item_id}
        if scene_uuid is not None:
            data["sceneUuid"] = scene_uuid
        return await self.request("GetSceneItemTransform", data)

    async def set_scene_item_transform(
        self,
        scene_name: str,
        scene_item_id: int,
        scene_item_transform: dict,
        scene_uuid: Optional[str] = None,
    ) -> None:
        data: dict = {"sceneName": scene_name, "sceneItemId": scene_item_id, "sceneItemTransform": scene_item_transform}
        if scene_uuid is not None:
            data["sceneUuid"] = scene_uuid
        await self.request("SetSceneItemTransform", data)

    async def get_scene_item_enabled(
        self,
        scene_name: str,
        scene_item_id: int,
        scene_uuid: Optional[str] = None,
    ) -> dict:
        data: dict = {"sceneName": scene_name, "sceneItemId": scene_item_id}
        if scene_uuid is not None:
            data["sceneUuid"] = scene_uuid
        return await self.request("GetSceneItemEnabled", data)

    async def set_scene_item_enabled(
        self,
        scene_name: str,
        scene_item_id: int,
        scene_item_enabled: bool,
        scene_uuid: Optional[str] = None,
    ) -> None:
        data: dict = {"sceneName": scene_name, "sceneItemId": scene_item_id, "sceneItemEnabled": scene_item_enabled}
        if scene_uuid is not None:
            data["sceneUuid"] = scene_uuid
        await self.request("SetSceneItemEnabled", data)

    async def get_scene_item_locked(
        self,
        scene_name: str,
        scene_item_id: int,
        scene_uuid: Optional[str] = None,
    ) -> dict:
        data: dict = {"sceneName": scene_name, "sceneItemId": scene_item_id}
        if scene_uuid is not None:
            data["sceneUuid"] = scene_uuid
        return await self.request("GetSceneItemLocked", data)

    async def set_scene_item_locked(
        self,
        scene_name: str,
        scene_item_id: int,
        scene_item_locked: bool,
        scene_uuid: Optional[str] = None,
    ) -> None:
        data: dict = {"sceneName": scene_name, "sceneItemId": scene_item_id, "sceneItemLocked": scene_item_locked}
        if scene_uuid is not None:
            data["sceneUuid"] = scene_uuid
        await self.request("SetSceneItemLocked", data)

    async def get_scene_item_index(
        self,
        scene_name: str,
        scene_item_id: int,
        scene_uuid: Optional[str] = None,
    ) -> dict:
        data: dict = {"sceneName": scene_name, "sceneItemId": scene_item_id}
        if scene_uuid is not None:
            data["sceneUuid"] = scene_uuid
        return await self.request("GetSceneItemIndex", data)

    async def set_scene_item_index(
        self,
        scene_name: str,
        scene_item_id: int,
        scene_item_index: int,
        scene_uuid: Optional[str] = None,
    ) -> None:
        data: dict = {"sceneName": scene_name, "sceneItemId": scene_item_id, "sceneItemIndex": scene_item_index}
        if scene_uuid is not None:
            data["sceneUuid"] = scene_uuid
        await self.request("SetSceneItemIndex", data)

    # ---------- Outputs / VirtualCam / ReplayBuffer ----------
    async def get_virtual_cam_status(self) -> dict:
        return await self.request("GetVirtualCamStatus")

    async def toggle_virtual_cam(self) -> dict:
        return await self.request("ToggleVirtualCam")

    async def start_virtual_cam(self) -> None:
        await self.request("StartVirtualCam")

    async def stop_virtual_cam(self) -> None:
        await self.request("StopVirtualCam")

    async def get_replay_buffer_status(self) -> dict:
        return await self.request("GetReplayBufferStatus")

    async def toggle_replay_buffer(self) -> dict:
        return await self.request("ToggleReplayBuffer")

    async def start_replay_buffer(self) -> None:
        await self.request("StartReplayBuffer")

    async def stop_replay_buffer(self) -> None:
        await self.request("StopReplayBuffer")

    async def save_replay_buffer(self) -> None:
        await self.request("SaveReplayBuffer")

    async def get_last_replay_buffer_replay(self) -> dict:
        return await self.request("GetLastReplayBufferReplay")

    async def get_output_list(self) -> dict:
        return await self.request("GetOutputList")

    async def get_output_status(self, output_name: str) -> dict:
        return await self.request("GetOutputStatus", {"outputName": output_name})

    async def toggle_output(self, output_name: str) -> dict:
        return await self.request("ToggleOutput", {"outputName": output_name})

    async def start_output(self, output_name: str) -> None:
        await self.request("StartOutput", {"outputName": output_name})

    async def stop_output(self, output_name: str) -> None:
        await self.request("StopOutput", {"outputName": output_name})

    async def get_output_settings(self, output_name: str) -> dict:
        return await self.request("GetOutputSettings", {"outputName": output_name})

    async def set_output_settings(self, output_name: str, output_settings: dict) -> None:
        await self.request("SetOutputSettings", {"outputName": output_name, "outputSettings": output_settings})

    # ---------- Stream ----------
    async def get_stream_status(self) -> dict:
        return await self.request("GetStreamStatus")

    async def toggle_stream(self) -> dict:
        return await self.request("ToggleStream")

    async def start_stream(self) -> None:
        await self.request("StartStream")

    async def stop_stream(self) -> None:
        await self.request("StopStream")

    async def send_stream_caption(self, caption_text: str) -> None:
        await self.request("SendStreamCaption", {"captionText": caption_text})

    # ---------- Record ----------
    async def get_record_status(self) -> dict:
        return await self.request("GetRecordStatus")

    async def toggle_record(self) -> dict:
        return await self.request("ToggleRecord")

    async def start_record(self) -> None:
        await self.request("StartRecord")

    async def stop_record(self) -> dict:
        return await self.request("StopRecord")

    async def toggle_record_pause(self) -> None:
        await self.request("ToggleRecordPause")

    async def pause_record(self) -> None:
        await self.request("PauseRecord")

    async def resume_record(self) -> None:
        await self.request("ResumeRecord")

    async def create_record_chapter(self, chapter_name: Optional[str] = None) -> None:
        data = {}
        if chapter_name is not None:
            data["chapterName"] = chapter_name
        await self.request("CreateRecordChapter", data if data else None)

    # ---------- Media Inputs ----------
    async def get_media_input_status(
        self,
        input_name: Optional[str] = None,
        input_uuid: Optional[str] = None,
    ) -> dict:
        data: dict = {}
        if input_name is not None:
            data["inputName"] = input_name
        if input_uuid is not None:
            data["inputUuid"] = input_uuid
        return await self.request("GetMediaInputStatus", data if data else None)

    async def set_media_input_cursor(
        self,
        media_cursor: int,
        input_name: Optional[str] = None,
        input_uuid: Optional[str] = None,
    ) -> None:
        data: dict = {"mediaCursor": media_cursor}
        if input_name is not None:
            data["inputName"] = input_name
        if input_uuid is not None:
            data["inputUuid"] = input_uuid
        await self.request("SetMediaInputCursor", data)

    async def offset_media_input_cursor(
        self,
        media_cursor_offset: int,
        input_name: Optional[str] = None,
        input_uuid: Optional[str] = None,
    ) -> None:
        data: dict = {"mediaCursorOffset": media_cursor_offset}
        if input_name is not None:
            data["inputName"] = input_name
        if input_uuid is not None:
            data["inputUuid"] = input_uuid
        await self.request("OffsetMediaInputCursor", data)

    async def trigger_media_input_action(
        self,
        media_action: Union[str, models.OBSEventType.ObsMediaInputAction],
        input_name: Optional[str] = None,
        input_uuid: Optional[str] = None,
    ) -> None:
        action = media_action if isinstance(media_action, models.OBSEventType.ObsMediaInputAction) else media_action
        data: dict = {"mediaAction": action}
        if input_name is not None:
            data["inputName"] = input_name
        if input_uuid is not None:
            data["inputUuid"] = input_uuid
        await self.request("TriggerMediaInputAction", data)

    # ---------- UI ----------
    async def get_studio_mode_enabled(self) -> dict:
        return await self.request("GetStudioModeEnabled")

    async def set_studio_mode_enabled(self, studio_mode_enabled: bool) -> None:
        await self.request("SetStudioModeEnabled", {"studioModeEnabled": studio_mode_enabled})

    async def open_input_properties_dialog(
        self,
        input_name: Optional[str] = None,
        input_uuid: Optional[str] = None,
    ) -> None:
        data: dict = {}
        if input_name is not None:
            data["inputName"] = input_name
        if input_uuid is not None:
            data["inputUuid"] = input_uuid
        await self.request("OpenInputPropertiesDialog", data if data else None)

    async def open_input_filters_dialog(
        self,
        input_name: Optional[str] = None,
        input_uuid: Optional[str] = None,
    ) -> None:
        data: dict = {}
        if input_name is not None:
            data["inputName"] = input_name
        if input_uuid is not None:
            data["inputUuid"] = input_uuid
        await self.request("OpenInputFiltersDialog", data if data else None)

    async def get_monitor_list(self) -> dict:
        return await self.request("GetMonitorList")

    # ---------- Sources (screenshot 等) ----------
    async def get_source_active(
        self,
        source_name: Optional[str] = None,
        source_uuid: Optional[str] = None,
    ) -> dict:
        data: dict = {}
        if source_name is not None:
            data["sourceName"] = source_name
        if source_uuid is not None:
            data["sourceUuid"] = source_uuid
        return await self.request(models.OBSEventType.SourceEventType.SOURCE_ACTIVE, data if data else None)

    async def get_source_screenshot(
        self,
        source_name: Optional[str] = None,
        source_uuid: Optional[str] = None,
        image_format: Optional[str] = None,
        image_width: Optional[int] = None,
        image_height: Optional[int] = None,
        image_compression_quality: Optional[int] = None,
    ) -> dict:
        data: dict = {}
        if source_name is not None:
            data["sourceName"] = source_name
        if source_uuid is not None:
            data["sourceUuid"] = source_uuid
        if image_format is not None:
            data["imageFormat"] = image_format
        if image_width is not None:
            data["imageWidth"] = image_width
        if image_height is not None:
            data["imageHeight"] = image_height
        if image_compression_quality is not None:
            data["imageCompressionQuality"] = image_compression_quality
        return await self.request(models.OBSEventType.SourceEventType.SOURCE_SCREENSHOT, data if data else None)

    # ---------- 兼容旧接口：仅发送不等待 ----------
    async def _request_event(self, event_name: str = "SetCurrentProgramScene", request_data: Optional[dict] = None) -> None:
        await self.request(event_name, request_data or {})
