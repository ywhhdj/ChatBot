from typing import Optional, TypeVar, Generic, Any
from dataclasses import dataclass

T = TypeVar("T", bound=object)

@dataclass
class ResponseData(Generic[T]):
    code: int
    data: Optional[T]
    message: str
    status: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "data": self.data,
            "message": self.message,
            "status": self.status
        }

@dataclass
class CodeDefinition:
    code:int
    message:str

class ResponseCode:
    OK = CodeDefinition(200, "OK")
    BAD_REQUEST = CodeDefinition(400, "Bad Request")
    INTERNAL_SERVER_ERROR = CodeDefinition(500, "未知的内部错误")
    UNAUTHORIZED = CodeDefinition(401, "未授权")
    NOT_FOUND = CodeDefinition(404, "未找到资源")

def success(data: Optional[T]=None,message: Optional[str] = None) -> dict:
    return ResponseData(
        code=ResponseCode.OK.code,
        data=data,
        message=message or ResponseCode.OK.message,
        status=True
    ).to_json()

def error(message: str,code: int=ResponseCode.BAD_REQUEST.code,data: Optional[T]=None) -> dict:
    return ResponseData(
        code=code,
        data=data,
        message=message,
        status=False,
    ).to_json()

def not_found(data: Optional[T]=None, message: Optional[str]=None) -> dict:
    if message is None:
        message = ResponseCode.NOT_FOUND.message
    return ResponseData(
        code=ResponseCode.NOT_FOUND.code,
        data=data,
        message=message,
        status=False
    ).to_json()

def unknown_error(data: Optional[T]=None, error: Optional[str]=None) -> dict:
    if error is None:
        error = ResponseCode.INTERNAL_SERVER_ERROR.message
    return ResponseData(
        code=ResponseCode.INTERNAL_SERVER_ERROR.code,
        data=data,
        message=error,
        status=False
    ).to_json()
    
