from dataclasses import asdict
from typing import Dict, List, Optional, Literal

from .driver import BrowserDriver
from ..base import _BaseService, ServiceState
from ...logger import logger
from ...events import on_event_class, types
from ...manager.service.decorator import Service
from .. import ServiceId
from .distiller import DOMDistiller
from .models import DistilledDOM

@on_event_class([
    (types.BrowserEventType.BROWSER_START, "start"),
    (types.BrowserEventType.BROWSER_STOP, "stop"),
])
@Service(id=ServiceId.BROWSER)
class Browser(_BaseService):
    name = "浏览器"
    description = "Playwright 驱动的浏览器服务，支持 DOM 蒸馏供 LLM 操作"

    def __init__(
        self,
        browser_type: str = "chrome",
        headless: bool = False,
        user_data_dir: Optional[str] = None,
        profile_name: str = "Default",
        cdp_url: Optional[str] = None,
        viewport: Optional[Dict[str, int]] = None,
        user_agent: Optional[str] = None,
        proxy: Optional[str] = None,
        distill_chunk_size: int = 20,
        distill_similarity: float = 0.88,
    ):
        super().__init__()
        self._driver = BrowserDriver(
            browser_type=browser_type,
            headless=headless,
            user_data_dir=user_data_dir,
            profile_dir=profile_name,
            cdp_url=cdp_url,
            user_agent=user_agent,
            viewport=viewport,
            proxy=proxy
        )
        self._page= None

        # DOM 蒸馏器
        self._distiller = DOMDistiller(
            max_chunk_size=distill_chunk_size,
            similarity_threshold=distill_similarity,
        )
        self.current_result=None
        self.running = False

    async def start(self, headless: bool = False) -> None:
        if self.running:
            logger.warning("[Browser] 已经在运行")
            return

        self._page = await self._driver.start_browser(
            headless=headless
        )
        await self._driver.inject_stealth()
        self.running = True
        self.set_status()
        logger.info(f"[Browser] ✅ 已启动 | URL: {self._page.url}")

    async def stop(self) -> None:
        if not self.running:
            return
        try:
            await self._driver.stop_browser()
        finally:
            self.running = False
            self.set_status()
            logger.info("[Browser] 🛑 已停止")

    def set_status(self):
        self.state = ServiceState.RUNNING if self.running else ServiceState.STOPPED


    async def open_page(
        self, url: str, 
        wait_until: Literal['commit', 'domcontentloaded', 'load', 'networkidle'] = 'domcontentloaded'
    ) -> None:
        if not self._page:
            raise RuntimeError("Browser not started")
        await self._page.goto(url, wait_until=wait_until, timeout=30000)
        logger.info(f"[Browser] 打开: {url}")

    async def go_back(self):
        if not self._page:
            raise RuntimeError("Browser not started")
        await self._page.go_back()

    async def go_forward(self):
        if not self._page:
            raise RuntimeError("Browser not started")
        await self._page.go_forward()

    async def reload(self):
        if not self._page:
            raise RuntimeError("Browser not started")
        await self._page.reload()

    async def distill_dom(self) -> DistilledDOM:
        """执行完整 7 级蒸馏，返回结构化结果"""
        if not self._page:
            raise RuntimeError("Browser not started")
        if self.current_result and self.current_url == self._page.url:
            return self.current_result
        title= await self.title()
        self.current_result = await self._distiller.distill_page(
            self._page,
            self.current_url,
            title
        )
        logger.info(
            f"[DOM] 原始={self.current_result.total_original_elements} "
            f"→ 过滤后={self.current_result.total_after_filter} "
            f"压缩率={self.current_result.compression_ratio*100:.1f}% "
            f"分块={len(self.current_result.chunks)}"
        )
        return self.current_result

    async def get_llm_context(
        self,
        chunk_index: int = 0
    ) -> str:
        """
        直接返回喂给 LLM 的字符串。
        默认返回第 0 块（视口内优先），可选附带全页摘要。
        """
        dom = await self.distill_dom()
        return self._distiller.format_for_llm(dom, chunk_index)

    async def get_all_chunks(self) -> List[Dict]:
        dom = await self.distill_dom()
        return [asdict(c) for c in dom.chunks]

    async def click(self, uid: str) -> bool:
        if not self._page:
            return False
        selector = await self._uid_to_selector(uid)
        if not selector:
            logger.warning(f"[Browser] click: 找不到 uid={uid} 的 selector")
            return False
        await self._page.click(selector)
        logger.info(f"[Browser] 点击: {uid} ({selector})")
        return True

    async def type_text(self, uid: str, text: str, submit: bool = False) -> bool:
        if not self._page:
            return False
        selector = await self._uid_to_selector(uid)
        if not selector:
            logger.warning(f"[Browser] type_text: 找不到 uid={uid} 的 selector")
            return False
        await self._page.fill(selector, text)
        if submit:
            await self._page.press(selector, "Enter")
        logger.info(f"[Browser] 输入: {uid} → {text[:30]}")
        return True

    async def get_text(self, uid: str) -> str:
        if not self._page:
            return ""
        selector = await self._uid_to_selector(uid)
        if not selector:
            return ""
        return await self._page.text_content(selector) or ""

    async def hover(self, uid: str) -> bool:
        if not self._page:
            return False
        selector = await self._uid_to_selector(uid)
        if not selector:
            return False
        await self._page.hover(selector)
        return True

    async def scroll(self, direction: str = "down", amount: int = 600):
        if not self._page:
            return
        logger.info(f"[Browser] 滚动: {direction} {amount}")
        if direction == "down":
            await self._page.evaluate(f"window.scrollBy(0, {amount})")
        else:
            await self._page.evaluate(f"window.scrollBy(0, -{amount})")


    async def screenshot(
        self,
        path: str = "screenshot.png",
        full_page: bool = False
    ) -> bytes:
        if not self._page:
            return b""
        if full_page:
            logger.info(f"[Browser] 截图: {path} (全页)")
        else:
            logger.info(f"[Browser] 截图: {path} (视口)")
        return await self._page.screenshot(path=path, full_page=full_page)

    async def _uid_to_selector(self, uid: str) -> Optional[str]:
        # 先查缓存
        if hasattr(self, '_uid_cache') and uid in self._uid_cache:
            return self._uid_cache[uid]

        # 缓存未命中 → 重新蒸馏
        try:
            dom = await self.distill_dom()
            self._uid_cache = {}
            for chunk in dom.chunks:
                for el in chunk.elements:
                    self._uid_cache[el.uid] = el.selector
            if uid in self._uid_cache:
                return self._uid_cache[uid]
        except Exception as e:
            logger.error(f"[Browser] uid 查找失败: {e}")

        # 兜底：如果 uid 本身就是合法 selector
        if uid.startswith(("#", ".", "/", "[")):
            return uid
        return None

    @property
    def page(self):
        return self._page

    @property
    def current_url(self) -> str:
        return self._page.url if self._page else ""

    async def title(self) -> str:
        return await self._page.title() if self._page else ""

    async def get_page_source(self) -> str:
        if not self._page:
            return ""
        html = await self._page.content()
        pos = html.find("<body")
        if pos != -1:
            html = html[pos:]
        return html.strip()[:50000]

    def get_tools(self) -> List[str]:
        return [
            "open_page",
            "click",
            "type_text",
            "get_text",
            "hover",
            "scroll",
            "screenshot",
            "go_back",
            "go_forward",
            "current_url",
            "title",
        ]