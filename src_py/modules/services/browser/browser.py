"""Playwright 驱动的浏览器服务，支持 DOM 蒸馏供 LLM 操作。
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Literal, Optional

from ...events import on_event_class, types
from ...logger import logger
from ...manager.service.decorator import Service
from ...pipeline.models import ToolFunction, ToolFunctionParameters
from ..keys import ServiceKeys
from ..base import BaseService, ServiceState

WaitUntil = Literal["commit", "domcontentloaded", "load", "networkidle"]


@on_event_class([
    (types.BrowserEventType.BROWSER_START, "start"),
    (types.BrowserEventType.BROWSER_STOP, "stop"),
])
@Service(id=ServiceKeys.BROWSER)
class Browser(BaseService):
    """Playwright 驱动的浏览器服务，支持 DOM 蒸馏供 LLM 操作。

    Parameters:
        browser_type: 浏览器类型，默认 "chrome"
        headless: 是否无头模式，默认 False
        user_data_dir: 用户数据目录，默认 None
        profile_name: 浏览器配置文件名称，默认 "Default"
        cdp_url: CDP URL，默认 None
        viewport: 视口大小，默认 None
        user_agent: 用户代理，默认 None
        proxy: 代理，默认 None
        distill_chunk_size: 蒸馏块大小，默认 20
        distill_similarity: 蒸馏相似度，默认 0.88
    """

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

        # 惰性依赖：playwright 缺失时本模块仍可导入、工具声明仍可读，
        # 只是 start() 会明确报错，不会让 ServiceManager 注册阶段就崩。
        try:
            from .driver import BrowserDriver
            from .distiller import DOMDistiller
        except ImportError as e:  # pragma: no cover
            logger.warning(f"[Browser] 依赖缺失，服务不可用: {e}")
            self._driver = None
            self._distiller = None
        else:
            self._driver = BrowserDriver(
                browser_type=browser_type,
                headless=headless,
                user_data_dir=user_data_dir,
                profile_dir=profile_name,
                cdp_url=cdp_url,
                user_agent=user_agent,
                viewport=viewport,
                proxy=proxy,
            )
            self._distiller = DOMDistiller(
                max_chunk_size=distill_chunk_size,
                similarity_threshold=distill_similarity,
            )

        self._page = None
        self.current_result = None
        self.running = False
        # S17：显式初始化
        self._uid_cache: Dict[str, str] = {}
        self._dom_version = 0

        self.set_status()

    # ---------- 状态 ----------

    def set_status(self, state = None) -> None:
        if state is None:
            state = "running" if self.running else "stopped"
        super().set_status(state)

    def _invalidate_cache(self) -> None:
        self.current_result = None
        self._uid_cache = {}
        self._dom_version += 1

    def _require_page(self):
        if not self._page:
            raise RuntimeError("Browser not started")
        return self._page

    # ---------- 生命周期 ----------

    async def start(self, headless: bool = False) -> None:
        if self.running:
            logger.warning("[Browser] 已经在运行")
            return
        if self._driver is None:
            raise RuntimeError("Browser 依赖缺失（playwright / driver 未安装）")

        self._page = await self._driver.start_browser(headless=headless)
        await self._driver.inject_stealth()
        self.running = True
        self._invalidate_cache()
        self.set_status()
        logger.info(f"[Browser] 已启动 | URL: {self.current_url}")

    async def stop(self) -> None:
        if not self.running:
            return
        try:
            await self._driver.stop_browser()  # type: ignore[union-attr]
        finally:
            self.running = False
            self._page = None
            self._invalidate_cache()
            self.set_status()
            logger.info("[Browser] 已停止")

    # ---------- 导航 ----------

    async def open_page(self, url: str, wait_until: WaitUntil = "domcontentloaded") -> None:
        page = self._require_page()
        await page.goto(url, wait_until=wait_until, timeout=30000)
        self._invalidate_cache()   # S52
        logger.info(f"[Browser] 打开: {url}")

    async def go_back(self) -> None:
        await self._require_page().go_back()
        self._invalidate_cache()

    async def go_forward(self) -> None:
        await self._require_page().go_forward()
        self._invalidate_cache()

    async def reload(self) -> None:
        await self._require_page().reload()
        self._invalidate_cache()

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

    # ---------- 蒸馏 ----------

    async def distill_dom(self):
        """执行完整 7 级蒸馏，返回结构化结果。"""
        page = self._require_page()
        url = self.current_url

        # S16：URL 相同但 DOM 版本变化时也要重新蒸馏
        if (
            self.current_result is not None
            and getattr(self.current_result, "url", None) == url
            and getattr(self.current_result, "version", None) == self._dom_version
        ):
            return self.current_result

        title = await self.title()
        result = await self._distiller.distill_page(page, url, title) # type: ignore[union-attr]
        try:
            result.url = url
            result.version = self._dom_version
        except Exception:
            pass
        self.current_result = result

        logger.info(
            f"[DOM] 原始={result.total_original_elements} "
            f"→ 过滤后={result.total_after_filter} "
            f"压缩率={result.compression_ratio * 100:.1f}% "
            f"分块={len(result.chunks)}"
        )
        return result

    async def get_llm_context(self, chunk_index: int = 0) -> str:
        """直接返回喂给 LLM 的字符串。默认返回第 0 块（视口内优先）。"""
        dom = await self.distill_dom()
        return self._distiller.format_for_llm(dom, chunk_index) # type: ignore[union-attr]

    async def get_all_chunks(self) -> List[Dict]:
        dom = await self.distill_dom()
        return [asdict(c) for c in dom.chunks]

    # ---------- 元素操作 ----------

    async def _uid_to_selector(self, uid: str) -> Optional[str]:
        # S17：缓存已初始化，直接查
        selector = self._uid_cache.get(uid)
        if selector:
            return selector

        try:
            dom = await self.distill_dom()
        except Exception as e:
            logger.error(f"[Browser] uid 查找失败: {e}")
            self._uid_cache = {}
            dom = None

        if dom is not None:
            self._uid_cache = {}
            for chunk in dom.chunks:
                for el in chunk.elements:
                    self._uid_cache[el.uid] = el.selector
            if uid in self._uid_cache:
                return self._uid_cache[uid]

        # 兜底：uid 本身可能是合法 selector
        if uid.startswith(("#", ".", "/", "[")):
            return uid
        return None

    async def click(self, uid: str) -> bool:
        if not self._page:
            return False
        selector = await self._uid_to_selector(uid)
        if not selector:
            logger.warning(f"[Browser] click: 找不到 uid={uid} 的 selector")
            return False
        await self._page.click(selector)
        self._dom_version += 1   # S16：DOM 可能变了
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
        self._dom_version += 1
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

    async def scroll(self, direction: str = "down", amount: int = 600) -> None:
        if not self._page:
            return
        logger.info(f"[Browser] 滚动: {direction} {amount}")
        # 滚动会改变视口内元素集合 → 失效缓存（S16）
        self._dom_version += 1
        if direction == "down":
            await self._page.evaluate(f"window.scrollBy(0, {amount})")
        else:
            await self._page.evaluate(f"window.scrollBy(0, -{amount})")

    async def screenshot(self, path: str = "screenshot.png", full: bool = False) -> bytes:
        if not self._page:
            return b""
        # S21：父目录不存在时 Playwright 会直接抛错
        target = Path(path)
        if target.parent and not target.parent.exists():
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
        logger.info(f"[Browser] 截图: {path} ({'全页' if full else '视口'})")
        return await self._page.screenshot(path=str(target), full_page=full)

    # ---------- 属性 ----------

    @property
    def page(self):
        return self._page

    @property
    def current_url(self) -> str:
        return self._page.url if self._page else ""

    # ---------- 工具声明 ----------

    def get_tools(self) -> List[ToolFunction]:
        return [
            ToolFunction(
                name="open_page",
                description="在浏览器中打开指定网址",
                parameters=ToolFunctionParameters(
                    type="object",
                    properties={
                        "url": {"type": "string", "description": "要打开的完整网址"},
                        "wait_until": {
                            "type": "string",
                            "description": "等待条件: commit/domcontentloaded/load/networkidle",
                        },
                    },
                    required=["url"],
                ),
            ),
            ToolFunction(
                name="click",
                description="点击页面元素",
                parameters=ToolFunctionParameters(
                    type="object",
                    properties={
                        "uid": {"type": "string", "description": "蒸馏结果中的元素 uid，如 pw-003"},
                    },
                    required=["uid"],
                ),
            ),
            ToolFunction(
                name="type_text",
                description="向输入框输入文本",
                parameters=ToolFunctionParameters(
                    type="object",
                    properties={
                        "uid": {"type": "string", "description": "输入框元素 uid"},
                        "text": {"type": "string", "description": "要输入的文本"},
                        "submit": {"type": "boolean", "description": "输入后是否按回车提交"},
                    },
                    required=["uid", "text"],
                ),
            ),
            ToolFunction(
                name="get_text",
                description="读取指定元素的文本内容",
                parameters=ToolFunctionParameters(
                    type="object",
                    properties={
                        "uid": {"type": "string", "description": "元素 uid"},
                    },
                    required=["uid"],
                ),
            ),
            ToolFunction(
                name="hover",
                description="鼠标悬停在指定元素上",
                parameters=ToolFunctionParameters(
                    type="object",
                    properties={
                        "uid": {"type": "string", "description": "元素 uid"},
                    },
                    required=["uid"],
                ),
            ),
            ToolFunction(
                name="scroll",
                description="滚动页面",
                parameters=ToolFunctionParameters(
                    type="object",
                    properties={
                        "direction": {"type": "string", "description": "滚动方向: down 或 up"},
                        "amount": {"type": "integer", "description": "滚动像素数，默认 600"},
                    },
                    required=["direction"],
                ),
            ),
            ToolFunction(
                name="screenshot",
                description="对当前页面截图",
                parameters=ToolFunctionParameters(
                    type="object",
                    properties={
                        "path": {"type": "string", "description": "截图保存路径"},
                        "full": {"type": "boolean", "description": "是否截取整页"},
                    },
                    required=[],
                ),
            ),
            ToolFunction(
                name="go_back",
                description="浏览器后退一页",
            ),
            ToolFunction(
                name="go_forward",
                description="浏览器前进一页",
            ),
            ToolFunction(
                name="reload",
                description="重新加载当前页面",
            ),
            ToolFunction(
                name="current_url",
                description="获取当前页面地址",
            ),
            ToolFunction(
                name="title",
                description="获取当前页面标题",
            ),
            ToolFunction(
                name="get_llm_context",
                description="获取页面蒸馏后可直接喂给 LLM 的交互元素表",
                parameters=ToolFunctionParameters(
                    type="object",
                    properties={
                        "chunk_index": {"type": "integer", "description": "分块序号，默认 0"},
                    },
                    required=[],
                ),
            ),
        ]
