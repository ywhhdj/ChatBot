import asyncio
from csv import QUOTE_MINIMAL, writer
import os
from threading import Lock
import time
from typing import Any, Dict, List, Literal, Union

from ....logger import logger
from ....utils.file import write_json


class SreachEngine:
    _instance=None
    _initialized=False
    _lock=Lock()
    
    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, engine_name: Union[Literal["bing","baidu"], str] = "bing"):
        if self._initialized:
            return
        self.engine_name = engine_name
        self.EngineSearch = self.__create_engine_search(engine_name)
        self.results: List[Dict[str, Any]] = []
        self._cache = {}
        self._cache_timeout = 300  # 5分钟缓存
        self._initialized = True

    def get_tools(self) -> list:
        return [
            "query"
        ]

    def __create_engine_search(self, engine_name: str):
        if engine_name=="bing":
            from .adapter import BingSearch
            return BingSearch()
        else:
            raise ValueError(f"不支持的搜索引擎：{engine_name}")

    async def query(self, keyword: str, page: int = 1, use_cache: bool = True, **kwargs) -> List[Dict[str, Any]]:
        cache_key = f"{self.engine_name}:{keyword}:{page}"
        # 检查缓存
        if use_cache and cache_key in self._cache:
            cached_data, timestamp = self._cache[cache_key]
            if time.time() - timestamp < self._cache_timeout:
                logger.info(f"📦 使用缓存结果: {cache_key}")
                return cached_data
        logger.info(f"🌐 URL: {self.EngineSearch} 查询：{keyword}，第{page}页")
        #如果没有关键词
        if not keyword:
            logger.error("请输入关键词")
            return []
        self.results = await self.EngineSearch.query(keyword, page, **kwargs)
        if use_cache:
            self._cache[cache_key] = (self.results.copy(), time.time())
        return self.results
    
    def save(self, file_name:str,type:Literal["csv","json"]="csv"):
        if type=="csv":
            return self.save_csv(file_name)
        elif type=="json":
            return self.save_json(file_name)
        else:
            raise ValueError(f"不支持的文件类型：{type}")
    
    def save_json(self, file_name:str):
        write_json(file_name,self.results)
        logger.info(f"💾 结果已保存至: {file_name}")

    def save_csv(self, file_name: str) -> bool:
        if not self.results:
            logger.error("没有查询结果")
            return False
        try:
            os.makedirs(os.path.dirname(file_name) or '.', exist_ok=True)
            with open(file_name, "w", encoding="utf-8-sig") as f:
                w = writer(f, delimiter=",", quotechar='"', quoting=QUOTE_MINIMAL)
                w.writerow(["序号"]+self.EngineSearch.get_result_header())
                for index, item in enumerate(self.results):
                    w.writerow([
                        index,
                        item.get('title', ''),
                        item.get('url', ''),
                        item.get('description', ''),
                        item.get('source', '')
                    ])
            logger.info(f"💾 结果已保存至: {file_name}")
            return True
        except Exception as e:
            logger.error(f"保存CSV文件出错: {e}")
            return False

    def clear_cache(self):
        self._cache.clear()
        logger.info("🧹 查询缓存已清除")