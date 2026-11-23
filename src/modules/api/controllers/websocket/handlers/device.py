"""设备帧 handler：收帧 → 角色/动作路由 → 按 uid/device 定向出站，不写业务规则。

三端链路（docs/api.md ）：
  mobile --fling_out--> server --jump_in--> desktop（电脑端人物跳入）
  mobile --peek_back / return_idle / turn_* / pose--> desktop（同步演出/转向）
  desktop --jump_out--> mobile（手机端人物跳出）
  mobile --device.text_input / record.audio_chunk(ASR)--> desktop（打字/语音送给电脑端）
"""

from typing import Any, Dict, List

from ..... import events
from .....devices import role_registry, stage_router
from .....debug import probe

_et = events.types.WebSocketEventType
DEVICE_EVENTS = _et.device_events()


def _source_role(manager, client_id: str) -> str:
    role = role_registry.role_of(client_id)
    if role in ("mobile", "desktop"):
        return role
    registered_device = manager.device_of(client_id)
    if registered_device in ("mobile", "desktop"):
        role_registry.set_role(client_id, registered_device, uid=manager.uid_of(client_id))
        return registered_device
    return "unknown"


async def _send_to_role(
    manager,
    client_id: str,
    uid: str,
    role: str,
    out_type: str,
    payload: Dict[str, Any],
    primary_only: bool,
) -> int:
    """优先走 send_to_device(uid, role)；未注册连接回退到旧角色表，绝不回灌自己。"""
    sent = 0
    if uid:
        sent = await manager.send_to_device(
            uid, role, out_type, payload,
            primary_only=primary_only, exclude=client_id, from_id=client_id,
        )
        if sent:
            return sent
    for cid in role_registry.targets(
        manager.active_connections, role,
        primary_only=primary_only, manager=manager,
        source_client_id=client_id,
    ):
        if cid == client_id:
            continue
        ok = await manager.send_json(
            cid, type=out_type, data=payload, from_id=client_id
        )
        if ok:
            sent += 1
            if primary_only:
                break
    return sent


def _fallback_pose_payload(data: Dict[str, Any], client_id: str, uid: str) -> Dict[str, Any]:
    return {
        "alpha": float(data.get("alpha") or 0.0),
        "beta": float(data.get("beta") or 0.0),
        "gamma": float(data.get("gamma") or 0.0),
        "seq": int(data.get("seq") or 0),
        "epoch": int(data.get("epoch") or 0),
        "t": int(data.get("t") or 0),
        "from_id": client_id,
        "uid": uid,
    }


async def dispatch_device(manager, client_id: str, event: str, data: dict) -> None:
    payload_in: Dict[str, Any] = data if isinstance(data, dict) else {}
    uid = manager.uid_of(client_id)
    role = _source_role(manager, client_id)

    # 客户端可显式指定 target_uid / target_device（ui 的 sendToDevice 便捷方法）。
    # 安全边界：只能指向自己的 uid，禁止借设备帧跨用户定向。
    requested_uid = str(payload_in.get("target_uid") or "")[:64]
    effective_uid = requested_uid if (not uid or requested_uid == uid) else uid
    requested_role = str(payload_in.get("target_device") or "")
    if requested_role not in ("mobile", "desktop"):
        requested_role = ""

    # ---- 姿态流：seq/epoch 去重后只推给电脑端 ----
    if event == _et.DEVICE_POSE:
        if not stage_router.check_pose(
            client_id, payload_in.get("epoch") or 0, payload_in.get("seq") or 0
        ):
            return
        pose_payload = _fallback_pose_payload(payload_in, client_id, uid)
        await _send_to_role(
            manager, client_id, effective_uid, requested_role or "desktop",
            _et.DEVICE_POSE, pose_payload, True,
        )
        probe.hit("pose")
        return

    # ---- 文本 / ASR 输入：手机说话或打字，实时送到电脑端 ----
    if event in (_et.DEVICE_TEXT_INPUT, _et.DEVICE_ASR_TEXT):
        text = str(payload_in.get("text") or payload_in.get("message") or "")[:2000]
        if not text.strip():
            await manager.send_json(
                client_id, type=_et.RESULT, ok=False, message="文本为空"
            )
            return
        out_payload = {
            "text": text,
            "source": str(payload_in.get("source") or "text"),
            "from": role,
            "from_id": client_id,
            "uid": uid,
            "seq": int(payload_in.get("seq") or 0),
            "t": int(payload_in.get("t") or payload_in.get("timestamp") or 0),
            "request_id": str(payload_in.get("request_id") or ""),
        }
        sent = await _send_to_role(
            manager, client_id, effective_uid, "desktop",
            _et.DEVICE_TEXT_INPUT, out_payload, True,
        )
        await manager.send_json(
            client_id, type=_et.RESULT,
            data={"accepted": sent > 0, "delivered": sent}, ok=True,
        )
        probe.hit("text_input")
        return

    # ---- 舞台动作 / 换模 / 通用动画 ----
    if event in (_et.DEVICE_STAGE_EVENT, _et.DEVICE_MODEL_SET,
                 _et.DEVICE_PLAY_ANIMATION):
        if event == _et.DEVICE_MODEL_SET:
            action_data: Dict[str, Any] = dict(payload_in, action="model_set")
        elif event == _et.DEVICE_PLAY_ANIMATION:
            action_data = dict(
                payload_in,
                action=str(payload_in.get("action") or "play_animation"),
            )
        else:
            action_data = payload_in

        plans: List = stage_router.translate(
            client_id, action_data, source_role=role, uid=uid
        )
        delivered = 0
        for out_type, out_payload, target_role, primary_only in plans:
            if target_role == "self":
                if out_payload.get("accepted") is False:
                    await manager.send_json(
                        client_id, type=_et.DEVICE_STAGE_EVENT,
                        data=out_payload, ok=False, message="未知动作",
                    )
                continue
            delivered += await _send_to_role(
                manager, client_id, effective_uid, requested_role or target_role,
                out_type, out_payload, bool(primary_only),
            )

        # 换模同时通知 Qt Live2D 服务；事件总线异常不影响主链路
        if event == _et.DEVICE_MODEL_SET:
            path = str(payload_in.get("model_path") or payload_in.get("path") or "")
            if path:
                try:
                    events.emit(events.types.Live2DEventType.LIVE2D_SET_MODEL, path)
                except Exception:
                    pass

        await manager.send_json(
            client_id, type=_et.RESULT,
            data={"accepted": delivered > 0 or bool(plans), "delivered": delivered},
            ok=True,
        )
        probe.hit("stage_event")
        return

    await manager.send_json(
        client_id, type=_et.ERROR, ok=False, message="未知设备事件",
    )
