from typing import Optional
import httpx

from .common import dtype,http_exceptions,parse_response

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

@http_exceptions(exception_message="GET request failed")
def get(
    url: str,
    params:Optional[dict] = None,
    headers: Optional[dict] = None,
    dtype:dtype="json",
    follow_redirects: bool = True,
    max_redirects: int = 5
):
    with create_httpx_sync_client(
        follow_redirects=follow_redirects,
        max_redirects=max_redirects
    ) as session:
        response=session.get(url,params=params,headers=headers)
        response.raise_for_status()
        return parse_response(response,dtype)

@http_exceptions(exception_message="POST request failed")
def post(
        url: str,
        data:Optional[dict] = None,
        headers: Optional[dict] = None,
        dtype:dtype="json",
        follow_redirects: bool = True,
        max_redirects: int = 5
    ):
    with create_httpx_sync_client(
        follow_redirects=follow_redirects,
        max_redirects=max_redirects
    ) as session:
        response=session.post(url,json=data,headers=headers)
        response.raise_for_status()
        return parse_response(response,dtype)