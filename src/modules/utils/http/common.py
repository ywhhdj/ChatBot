from functools import wraps
from inspect import iscoroutinefunction
from typing import Any, Literal, Union
import httpx

dtype=Union[Literal["json","str","bytes","html"],str]

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

def parse_response(response: httpx.Response, dtype: dtype) -> Any:
    if dtype == "json":
        return response.json()
    elif dtype == "bytes":
        return response.content
    elif dtype == "html":
        from lxml import html
        return html.fromstring(response.text)
    else:
        return response.text

