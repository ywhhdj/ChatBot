# 设备帧 handler：只做「收帧 -> 领域层 -> 定向出站」，不写业务规则。
from ..... import events
from .....devices import role_registry, stage_router
# from .....debug import probe

DEVICE_EVENTS = frozenset({
    events.types.WebSocketEventType.DEVICE_HELLO,
    events.types.WebSocketEventType.DEVICE_POSE,
    events.types.WebSocketEventType.DEVICE_STAGE_EVENT,
    events.types.WebSocketEventType.DEVICE_PLAY_ANIMATION,
    events.types.WebSocketEventType.DEVICE_MODEL_SET,
})


async def dispatch_device(manager, client_id: str, event: str, data: dict) -> None:
    et = events.types.WebSocketEventType
    active = manager.active_connections

    if event == et.DEVICE_HELLO:
        role = str(data.get('role') or 'mobile')
        role_registry.set_role(client_id, role)
        # probe.hit('hello')
        await manager.send_json(
            client_id, type=et.DEVICE_HELLO,
            data={
                'role': role,
                'client_id': client_id
            },
            ok=True, message='role registered',
        )
        return

    if event == et.DEVICE_POSE:
        epoch = int(data.get('epoch') or 0)
        seq = int(data.get('seq') or 0)
        if not stage_router.check_pose(client_id, epoch, seq):
            return
        probe.hit('pose')
        payload = {
            'alpha': float(data.get('alpha') or 0.0),
            'beta': float(data.get('beta') or 0.0),
            'gamma': float(data.get('gamma') or 0.0),
            'seq': seq, 't': int(data.get('t') or 0),
            'from_id': client_id,
        }
        for cid in role_registry.targets(active, 'desktop', primary_only=True):
            await manager.send_json(cid, type=et.DEVICE_POSE, data=payload, ok=True)
        return

    if event in (et.DEVICE_STAGE_EVENT, et.DEVICE_MODEL_SET, et.DEVICE_PLAY_ANIMATION):
        if event == et.DEVICE_MODEL_SET:
            action_data = dict(data, action='model_set')
        elif event == et.DEVICE_PLAY_ANIMATION:
            action_data = dict(data, action=str(data.get('action') or 'jump_out'))
        else:
            action_data = data
        plans = stage_router.translate(client_id, action_data)
        for out_type, payload, target_role, primary_only in plans:
            if target_role == 'self':
                await manager.send_json(client_id, type=et.DEVICE_STAGE_EVENT,
                                        data=payload, ok=False, message='未知动作')
                continue
            for cid in role_registry.targets(active, target_role, primary_only):
                if cid == client_id:       # U07：绝不回灌自己
                    continue
                await manager.send_json(cid, type=out_type, data=payload, ok=True)
        # 换模同时通知 Qt Live2D 服务（S4.6）；事件总线异常不影响主链路。
        if event == et.DEVICE_MODEL_SET:
            path = str(data.get('model_path') or '')
            if path:
                try:
                    events.emit(events.types.Live2DEventType.LIVE2D_SET_MODEL, path)
                except Exception:
                    pass
        probe.hit('stage_event')
        await manager.send_json(client_id, type=et.RESULT,
                                data={'accepted': bool(plans)}, ok=True)
        return

    await manager.send_json(client_id, type=et.ERROR, ok=False, message='未知设备事件')
