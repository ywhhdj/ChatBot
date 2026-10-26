import os
from pathlib import Path
from typing import Callable, Optional,Any
import httpx
from inspect import iscoroutinefunction

from .common import dtype,http_exceptions,parse_response

def create_httpx_async_client(
    max_connections: int = 100,
    timeout: float = 10,
    follow_redirects: bool = True,
    max_redirects: int = 3
):
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout),
        limits=httpx.Limits(max_connections=max_connections),
        max_redirects=max_redirects,
        follow_redirects=follow_redirects
    )

@http_exceptions(exception_message="Download file failed")
async def download_file(
    url: str,
    save_path: Path,
    method: str = "GET",
    headers: Optional[dict] = None,
    chunk_size: int = 10264,
    progress_callback: Optional[Callable[[int], Any]] = None,
    follow_redirects: bool = True,
    max_redirects: int = 5,
    client: Optional[httpx.AsyncClient] = None
):
    if client is None:
        client = create_httpx_async_client(
            follow_redirects=follow_redirects,
            max_redirects=max_redirects
        )
    async with client:
        async with client.stream(method, url, params=None, headers=headers) as response:
            response.raise_for_status()
            if save_path.suffix == '':
                filename = url.split('/')[-1]
                save_path = save_path / filename
                os.makedirs(save_path.parent, exist_ok=True)
            total_size = int(response.headers.get("content-length"))
            downloaded_size = 0
            with open(save_path, "wb") as f:
                if total_size > 0:
                    if progress_callback is None:
                        from tqdm import tqdm
                        with tqdm(unit="B", unit_scale=True, desc=f"Downloading {filename}") as pbar:
                                for chunk in response.iter_bytes(chunk_size=chunk_size):
                                    if chunk:
                                        f.write(chunk)
                                        pbar.update(len(chunk))
                                        downloaded_size += len(chunk)
                    else:
                        for chunk in response.iter_bytes(chunk_size=chunk_size):
                            if chunk:
                                f.write(chunk)
                                downloaded_size += len(chunk)
                                progress=int((total_size/downloaded_size)*100)
                                if iscoroutinefunction(progress_callback):
                                    await progress_callback(progress)
                                else:
                                    progress_callback(progress)
@http_exceptions(exception_message="POST request failed")
async def async_post(
    url: str,
    data: Optional[Any]=None,
    headers: Optional[dict] = None,
    dtype:dtype="bytes",
    follow_redirects: bool = True,
    max_redirects: int = 5
):
    async with create_httpx_async_client(
        follow_redirects=follow_redirects,
        max_redirects=max_redirects
    )as session:
        response=await session.post(url,json=data, headers=headers)
        response.raise_for_status()
        return parse_response(response,dtype)

@http_exceptions(exception_message="GET request failed")
async def async_get(
    url: str,
    params:Optional[dict] = None,
    headers: Optional[dict] = None,
    dtype:dtype="bytes",
    follow_redirects: bool = True,
    max_redirects: int = 5
):
    async with create_httpx_async_client(
        follow_redirects=follow_redirects,
        max_redirects=max_redirects
    )as session:
        response=await session.get(url,params=params, headers=headers)
        response.raise_for_status()
        return parse_response(response,dtype)