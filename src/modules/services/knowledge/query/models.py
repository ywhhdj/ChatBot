from typing import TypedDict

class BingSearchParamsParamters:
    class Form:
        default = "QBLH"
        enhanced = "QBRE"

    class SafeSearch:
        strict = "Strict"
        off = "Off"
        medium = "Moderate"

    class RequestParams(TypedDict):
        q:str #查询关键词
        first:int #起始位置
        form:str #表单选项
        pq:str #上次查询参数
        safeSearch:str #安全搜索