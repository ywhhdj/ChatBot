from pathlib import Path
from typing import Any, Callable, Optional
from ...utils.http import download_file
from ...logger import logger
from ...core.native.decorator import async_task_scheduler

@async_task_scheduler
async def download_google_facelandmarker(
    save_path:str,
    progress_callback:Optional[Callable[[int],Any]]=None,
):
    download_model_url = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
    try:
        await download_file(download_model_url,Path(save_path),progress_callback=progress_callback)
    except Exception as e:
        logger.error(f"模型下载失败: {e}")

