from typing import Optional
from fastapi import APIRouter,Query

from ...services import ServiceId,ServiceState
from ...utils import response
from ...events import emit,BaseEvent,types
from ...manager.service.manager import service_manager


service_router = APIRouter(prefix="/service")

@service_router.get("/config")
def get_service_config_info(name: Optional[str] = Query(None,description="服务名称")):
    if name:
        service_info=service_manager.get_service_info(name)
        if service_info:
            return response.success(service_info)
        else:
            return response.error(message=f"service {name} not registered")
    return response.success(service_manager.get_default_services_description())

@service_router.post("/start")
def start_service(playload):
    service_id=playload.get("id")
    if not service_id:
        return response.not_found("id 参数缺失")
    service_registered=service_manager.is_registered(service_id)
    if  not service_registered:
        return response.error(message=f"service {service_id} not registered")
    elif service_registered and service_manager.get_service_state(service_id)==ServiceState.RUNNING:
        return response.error(message=f"service {service_id} already started")
    event={
        ServiceId.LIVE2D:types.Live2DEventType.LIVE2D_START,
        ServiceId.OBS:types.ObsEventType.OBS_CONNECT,
        ServiceId.QQBOT:types.QQBotEventType.QQ_BOT_START,
        ServiceId.BROWSER:types.BrowserEventType.BROWSER_START,
    }
    event_type=event.get(service_id,"")
    if not event_type:
        return response.error(message=f"service {service_id} not found")
    emit(BaseEvent(type=event_type))
    return response.success(message="service started")

@service_router.post("/enable")
def enable_service(playload):
    service_id=playload.get("id")
    if not service_id:
        return response.not_found("id 参数缺失")
    service_registered=service_manager.is_registered(service_id)
    if  not service_registered:
        config=playload.get("config")
        if not config:
            return response.not_found("config 参数缺失")
        if service_id==ServiceId.LIVE2D:
            from ...services.live2d.views import Live2DView
            Live2DView(**config)
        elif service_id==ServiceId.OBS:
            from ...services.obs.client import OBSClient
            OBSClient(**config)
        elif service_id==ServiceId.QQBOT:
            from ...services.qqbot.client import QQBotClient
            QQBotClient(**config)
        elif service_id==ServiceId.BROWSER:
            from ...services.browser.browser import Browser
            Browser(**config)
        else:
            return response.error(message=f"service {service_id} not found")
    else:
        return response.error(message=f"service {service_id} already enabled")

@service_router.post("/stop")
def stop_service(playload):
    service_id=playload.get("id")
    if not service_id:
        return response.not_found("id 参数缺失")
    service_registered=service_manager.is_registered(service_id)
    if  not service_registered:
        return response.error(message=f"service {service_id} not registered")
    elif service_registered and service_manager.get_service_state(service_id)==ServiceState.STOPPED:
        return response.error(message=f"service {service_id} not running")
    event={
        ServiceId.LIVE2D:types.Live2DEventType.LIVE2D_STOP,
        ServiceId.OBS:types.ObsEventType.OBS_DISCONNECT,
        ServiceId.QQBOT:types.QQBotEventType.QQ_BOT_STOP,
        ServiceId.BROWSER:types.BrowserEventType.BROWSER_STOP,
    }
    event_type=event.get(service_id,"")
    if not event_type:
        return response.error(message=f"service {service_id} not found")
    emit(BaseEvent(type=event_type))
    return response.success(message="service stopped")

@service_router.get("/qqbot/info")
def get_qqbot_info():
    service_registered=service_manager.is_registered(ServiceId.QQBOT)
    if not service_registered:
        return response.error(message="qqbot not registered")
    if service_registered and service_manager.get_service_state(ServiceId.QQBOT)==ServiceState.RUNNING:
        result = emit(BaseEvent(type=types.QQBotEventType.QQ_BOT_INFO))
        if result:
            return response.success(data=result)
        else:
            return response.error(message="qqbot 返回空值")
    else:
        return response.error(message="qqbot not running")
