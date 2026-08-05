import asyncio
from inspect import iscoroutinefunction
from pathlib import Path
from typing import Any, Callable, Optional
from ...utils.http import create_httpx_async_client, download_file
from ...logger import logger
from ...manager.task.decorator import async_task_scheduler

@async_task_scheduler
async def download_paddle_ocr(
    save_path:str,
    progress_callback:Optional[Callable[[int],Any]]=None,
):
    download_model_urls = {
        "det": "https://paddleocr.bj.bcebos.com/dygraph_v2.0/ch/ch_ppocr_mobile_v2.0_det_infer.tar",
        "rec": "https://paddleocr.bj.bcebos.com/dygraph_v2.0/ch/ch_ppocr_mobile_v2.0_rec_infer.tar",
        "cls": "https://paddleocr.bj.bcebos.com/dygraph_v2.0/ch/ch_ppocr_mobile_v2.0_cls_infer.tar"
    }
    try:
        total_progress = {"downloaded": 0, "total": len(download_model_urls)}
        task=[]
        client = create_httpx_async_client()
        async def update_progress(progress: int):
            overall_progress = (
                    (total_progress["downloaded"] * 100 + progress) // 
                    (total_progress["total"] * 100)
                )
            if progress_callback is not None:
                 if iscoroutinefunction(progress_callback):
                    await progress_callback(overall_progress)
                 else:
                    progress_callback(overall_progress)
        for key, url in download_model_urls.items():
            task.append(download_file(
                url,Path(save_path) / key,
                client=client,
                progress_callback=update_progress
            ))
        await asyncio.gather(*task)
    except Exception as e:
        logger.error(f"模型下载失败: {e}")

@async_task_scheduler
async def download_umi_ocr(
    save_path:str,
    progress_callback:Optional[Callable[[int],Any]]=None,
):
    download_model_url = "https://github.com/hiroi-sora/Umi-OCR/releases/latest/download/models.zip"
    try:
        await download_file(download_model_url,Path(save_path),progress_callback=progress_callback)
    except Exception as e:
        logger.error(f"模型下载失败: {e}")