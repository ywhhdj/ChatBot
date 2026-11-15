
from ..... import events


async def handle_download_model(
    manager,
    client_id: str,
    data:dict
):
    model_name:str=data.get("model_name","")
    save_path: str = data.get("save_path","")
    if not model_name:
        await manager.send_json(
            client_id,
            type=events.types.DownloadEventType.ERROR,
            ok=False,
            message="缺少 model_name",
        )
        return
    from .....providers.manager import provider_manager

    async def _send(event_type: str, payload, ok: bool = True, message: str = "ok"):
        await manager.send_json(client_id, type=event_type, data=payload, message=message, ok=ok)

    parsed = _parse_download_target(model_name)
    if parsed is None:
        await _send(
            events.types.DownloadEventType.ERROR,
            {"model": model_name},
            ok=False,
            message="不支持该模型下载",
        )
        return

    capability, provider, model_id = parsed

    # 已安装检测
    status = provider_manager.get_provider_status(capability, provider, model_id)
    if status is None:
        await _send(
            events.types.DownloadEventType.ERROR,
            {"model": model_name, "capability": capability, "provider": provider},
            ok=False,
            message=f"provider {provider} 不存在或不支持下载",
        )
        return
    if status["download_status"].get("installed"):
        await _send(
            events.types.DownloadEventType.ERROR,
            {
                "model": model_name,
                "provider": provider
            },
            ok=False,
            message="模型已存在，无需下载",
        )
        return

    task_id = f"{capability}:{provider}:{model_id or ''}"

    async def _progress(evt: dict) -> None:
        phase = evt.get("phase")
        if phase == "complete":
            await _send(
                events.types.DownloadEventType.COMPLETED,
                {
                    "model": model_name,
                    "capability": capability,
                    "provider": provider,
                    "model_id": model_id,
                    "target_dir": evt.get("target_dir", ""),
                },
                ok=True,
                message="下载完成",
            )
            return
        await _send(
            events.types.DownloadEventType.RUNNING,
            {
                "model": model_name,
                "capability": capability,
                "provider": provider,
                "model_id": model_id,
                "progress": evt.get("progress", 0),
                "file": evt.get("file"),
                "phase": phase or "download",
            },
            ok=True,
            message=f"下载进度: {evt.get('progress', 0)}",
        )

    await _send(
        events.types.DownloadEventType.STARTED,
        {
            "model": model_name,
            "capability": capability,
            "provider": provider,
            "model_id": model_id,
            "task_id": task_id,
        },
        ok=True,
        message="开始下载",
    )

    try:
        result = await provider_manager.download_model(
            capability, provider, model_id,
            progress_callback=_progress,
        )
    except Exception as exc:  # noqa: BLE001
        await _send(
            events.types.DownloadEventType.FAILED,
            {"model": model_name, "capability": capability,
             "provider": provider, "error": str(exc)},
            ok=False,
            message=f"下载失败: {exc}",
        )
        return

    if not result.get("success"):
        await _send(
            events.types.DownloadEventType.FAILED,
            {"model": model_name, "capability": capability,
             "provider": provider, "error": result.get("error", "")},
            ok=False,
            message=f"下载失败: {result.get('error', '')}",
        )


def _parse_download_target(model_name: str):
    """解析下载目标。

    新格式：``"ocr:paddle"`` / ``"ocr:paddle:ppocr"`` / ``"image:comfyui-local"``。
    兼容别名：
      * ``paddle_ocr`` → (``ocr``, ``paddle``, None)
      * ``umi_ocr``    → (``ocr``, ``umi``, None)
      * ``whisper``    → (``asr``, ``whisper``, None)
    暂不支持的 ``google_facelandmarker`` 返回 None（由旧逻辑另行处理）。
    """
    if model_name == "google_facelandmarker":
        return None
    if model_name == "paddle_ocr":
        return ("ocr", "paddle", None)
    if model_name == "umi_ocr":
        return ("ocr", "umi", None)
    if model_name == "whisper":
        return ("asr", "whisper", None)
    parts = model_name.split(":")
    if len(parts) == 2:
        return (parts[0], parts[1], None)
    if len(parts) == 3:
        return (parts[0], parts[1], parts[2])
    return None
