from functools import wraps
import os
from pathlib import Path
from typing import Callable, Literal, Union
from typing import Optional, Union,Any
import httpx
from tqdm import tqdm
from inspect import iscoroutinefunction


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

def create_httpx_sync_client(
    max_connections: int = 100,
    timeout: float = 10,
    follow_redirects: bool = True,
    max_redirects: int = 3
):
    return httpx.Client(
        timeout=httpx.Timeout(timeout),
        limits=httpx.Limits(max_connections=max_connections),
        max_redirects=max_redirects,
        follow_redirects=follow_redirects
    )

def http_exceptions(func=None,exception_message: str = "Request failed"):
    def decorator(func):
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except httpx.ConnectTimeout:
                raise RuntimeError("ConnectTimeout")
            except httpx.RequestError:
                raise RuntimeError("RequestError")
            except httpx.HTTPStatusError as e:
                raise RuntimeError(f"HTTPStatusError: {e.response.status_code}")
            except httpx.HTTPError as e:
                raise RuntimeError(f"HTTPError: {e}")
            except Exception as e:
                raise RuntimeError(f"{exception_message}: {e}")

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except httpx.ConnectTimeout:
                raise RuntimeError("ConnectTimeout")
            except httpx.RequestError:
                raise RuntimeError("RequestError")
            except httpx.HTTPStatusError as e:
                raise RuntimeError(f"HTTPStatusError: {e.response.status_code}")
            except httpx.HTTPError as e:
                raise RuntimeError(f"HTTPError: {e}")
            except Exception as e:
                raise RuntimeError(f"{exception_message}: {e}")

        if iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    if func is None:
        return decorator
    return decorator(func)

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
                        with tqdm(total=total_size) as pbar:
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
                                process=int((total_size/downloaded_size)*100)
                                print(process,filename)
                                if iscoroutinefunction(progress_callback):
                                    await progress_callback(process)
                                else:
                                    progress_callback(process)
                else:
                    for chunk in response.iter_bytes(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            downloaded_size += len(chunk)

_dtype=Union[Literal["json","str","bytes","html"],str]

def __parse_response(response: httpx.Response, dtype: _dtype) -> Any:
    if dtype == "json":
        return response.json()
    elif dtype == "bytes":
        return response.content
    elif dtype == "html":
        from lxml import html
        return html.fromstring(response.text)
    else:
        return response.text

@http_exceptions(exception_message="GET request failed")
def get(
    url: str,
    params:Optional[dict] = None,
    headers: Optional[dict] = None,
    dtype:_dtype="json",
    follow_redirects: bool = True,
    max_redirects: int = 5
):
    with create_httpx_sync_client(
        follow_redirects=follow_redirects,
        max_redirects=max_redirects
    ) as session:
        response=session.get(url,params=params,headers=headers)
        response.raise_for_status()
        return __parse_response(response,dtype)

@http_exceptions(exception_message="POST request failed")
def post(
        url: str,
        data:Optional[dict] = None,
        headers: Optional[dict] = None,
        dtype:_dtype="json",
        follow_redirects: bool = True,
        max_redirects: int = 5
    ):
    with create_httpx_sync_client(
        follow_redirects=follow_redirects,
        max_redirects=max_redirects
    ) as session:
        response=session.post(url,json=data,headers=headers)
        response.raise_for_status()
        return __parse_response(response,dtype)

@http_exceptions(exception_message="POST request failed")
async def async_post(
    url: str,
    data: Optional[Any]=None,
    headers: Optional[dict] = None,
    dtype:_dtype="bytes",
    follow_redirects: bool = True,
    max_redirects: int = 5
):
    async with create_httpx_async_client(
        follow_redirects=follow_redirects,
        max_redirects=max_redirects
    )as session:
        response=await session.post(url,json=data, headers=headers)
        response.raise_for_status()
        return __parse_response(response,dtype)

@http_exceptions(exception_message="GET request failed")
async def async_get(
    url: str,
    params:Optional[dict] = None,
    headers: Optional[dict] = None,
    dtype:_dtype="bytes",
    follow_redirects: bool = True,
    max_redirects: int = 5
):
    async with create_httpx_async_client(
        follow_redirects=follow_redirects,
        max_redirects=max_redirects
    )as session:
        response=await session.get(url,params=params, headers=headers)
        response.raise_for_status()
        return __parse_response(response,dtype)