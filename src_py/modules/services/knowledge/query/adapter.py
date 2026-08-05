from abc import ABC, abstractmethod
from typing import Coroutine
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from bs4 import BeautifulSoup

from ....utils.http import async_get
from . import models

class _EngineSearch(ABC):
    def __init__(self):
        super().__init__()
        self.params=None

    def get_search_params(self) -> dict:
        return self.params.__dict__

    @abstractmethod
    def query(self, keyword: str, page: int = 1,**params) -> Coroutine:
        raise NotImplementedError
    
    @abstractmethod
    def get_result_header(self) -> list[str]:
        raise NotImplementedError
    
    @abstractmethod
    def get_search_url(self) -> str:
        raise NotImplementedError

class BingSearch(_EngineSearch):
    def __init__(self):
        super().__init__()
        self.last_keyword=""
        self.base_url="https://cn.bing.com/search"
        self.params=models.BingSearchParamsParamters.RequestParams(
            q="",
            first=1,
            form=models.BingSearchParamsParamters.Form.default,
            pq=self.last_keyword,
            safeSearch=models.BingSearchParamsParamters.SafeSearch.off
        )
        self.page_count=10
        self.results=[]
        self.__url_pattern = re.compile(r'^https?://')
    
    def get_search_url(self) -> str:
        return self.base_url
    
    async def query(self,keyword:str,page:int=1,page_count:int=10) -> List[Dict[str,Any]]:
        self.last_keyword=self.params["q"]
        self.params["q"]=keyword
        if page==1:
            self.params["first"]=1
        else:
            self.params["first"]=(page-1)*page_count+1
        self.params["pq"]=keyword
        result= await async_get(
            self.base_url,
            params=self.get_search_params(),
            dtype="html"
        )
        if isinstance(result,BeautifulSoup):
            results =  self.get_search_results(result) or []
            return results
        return []
    
    def get_result_header(self) -> list[str]:
        return ["title","url","description","source"]

    def get_search_results(self, result: BeautifulSoup) -> Optional[List[Dict[str, Any]]]:
        self.results = []
        result_items = result.find_all("li", class_="b_algo")
        for li in result_items:
            try:
                item = self.__parse_single_result(li)
                if item:
                    self.results.append(item)
            except Exception as e:
                return None
        return self.results

    def __parse_single_result(self, li: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """解析单个搜索结果"""
        # 1. 标题和链接
        h2 = li.find("h2")
        if not h2:
            return None
        a_tag = h2.find("a")
        if not a_tag:
            return None
        title = a_tag.get_text(strip=True) # type: ignore
        url = a_tag.get("href") # type: ignore
        # 验证URL
        if not url or not self.__url_pattern.match(str(url)):
            return None
        # 2. 描述
        caption = li.find("div", class_="b_caption")
        desc = ""
        if caption:
            # 尝试多种方式获取描述
            p = caption.find("p", class_="b_lineclamp2") # type: ignore
            if p:
                desc = p.get_text(strip=True)
            else:
                desc = caption.get_text(strip=True)[:200]  # 限制长度
        # 3. 来源网站
        source = self.__extract_source(li, url) # type: ignore
        return {
            "title": title,
            "url": url,
            "description": desc,
            "source": source
        }

    def __extract_source(self, li: BeautifulSoup, url: str) -> str:
        """提取来源网站"""
        # 尝试从页面元素获取
        tpcn = li.find("div", class_="b_tpcn")
        if tpcn:
            tptt = tpcn.find("div", class_="tptt") # type: ignore
            if tptt:
                return tptt.get_text(strip=True)
            cite = tpcn.find("cite")
            if cite:
                return cite.get_text(strip=True) # type: ignore
        # 从URL提取域名
        try:
            parsed = urlparse(url)
            return parsed.netloc
        except:
            return ""
