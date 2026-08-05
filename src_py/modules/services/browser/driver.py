from typing import Dict, Optional, Literal
from playwright.async_api import (
    async_playwright, Playwright, Browser, BrowserContext, Page
)

from src_py.modules.runtime import RuntimePath
from src_py.modules.utils.file import read_text
from ...logger import logger

BrowserType = Literal["chrome", "edge", "firefox"]

class BrowserDriver:
    """
    统一管理 Playwright 浏览器实例的生命周期

    三种模式：
      1. launch()         —— 启动全新浏览器（自动下载）
      2. launch_persistent() —— 用用户 profile 启动
      3. connect_cdp()    —— 连接已运行的浏览器
    """

    def __init__(
        self,
        browser_type: BrowserType|str = "chrome",
        profile_dir: Optional[str] = None,
        cdp_url: Optional[str] = None,
        user_agent: Optional[str] = None,
        user_data_dir: Optional[str] = None,
        headless: bool = True,
        browser_name: str = "chrome",
        viewport: Optional[Dict[str, int]] = None,
        proxy: str|None = None,
    ):
        from ..config import BrowserConfig
        if isinstance(browser_type, str) and browser_type in ["chrome", "edge", "firefox"]:
            browser_type = browser_type
        else:
            raise ValueError(f"Invalid browser type: {browser_type}")
        self.config = BrowserConfig(
            enabled=True,
            browser_type=browser_type,
            headless=headless,
            user_data_dir=user_data_dir or "",
            profile_name=profile_dir or "",
            cdp_url=cdp_url or "",
            viewport=viewport or {
                "width": 1280,
                "height": 800
            },
            user_agent=user_agent or (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            proxy=proxy
        )
        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
    
    def build_args(self) -> list[str]:
        args= [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--window-size=1280,800",
            "--enable-unsafe-swiftshader",
            "--use-gl=swiftshader",
            "--ignore-gpu-blocklist"
        ]
        return args

    async def start_browser(self, headless: bool = False) -> Page:
        self._pw = await async_playwright().start()

        if self.config.cdp_url:
            self._browser = await self.__get_launcher().connect_over_cdp(self.config.cdp_url)
            self._context = self._browser.contexts[0] if self._browser.contexts else await self._browser.new_context()
        elif self.config.profile_name:
            args = self.build_args()
            self._context = await self.__get_launcher().launch_persistent_context(
                user_data_dir=self.config.user_data_dir,
                channel=self.__get_channel(),
                headless=headless,
                viewport={"width": 1280, "height": 800},
                user_agent=self.config.user_agent,
            )
            self._browser = self._context.browser
        else:
            self._browser = await self.__get_launcher().launch(
                headless=headless,
                channel=self.__get_channel(),
            )
            self._context = await self._browser.new_context(
                viewport={"width": 1280, "height": 800},
            )

        self._page = self._context.pages[0] if self._context.pages else await self.new_page()
        logger.info(f"[BrowserDriver] ✅ 已启动 {self.config.browser_type} | {self._page.url}")
        return self._page

    async def stop_browser(self):
        try:
            if self._context and not self.config.cdp_url:
                await self._context.close()
            if self._browser and not self.config.cdp_url:
                await self._browser.close()
            if self._pw:
                await self._pw.stop()
        except Exception as e:
            logger.error(f"[BrowserDriver] 关闭异常: {e}")
        finally:
            self._pw = None
            self._browser = None
            self._context = None
            self._page = None
            logger.info("[BrowserDriver] 🛑 已停止")

    async def new_page(self) -> Page:
        if not self._context:
            raise RuntimeError("Browser not started. Call start() first.")
        return await self._context.new_page()

    async def inject_stealth(self):
        if self._context:
            stealth =read_text(RuntimePath.get_scripts_path("stealth.js"))
            await self._context.add_init_script(stealth)
            logger.info("[BrowserDriver] 🕵️ 反检测脚本已注入")

    @property
    def page(self) -> Optional[Page]:
        return self._page

    @property
    def context(self) -> Optional[BrowserContext]:
        return self._context

    @property
    def browser(self) -> Optional[Browser]:
        return self._browser

    @property
    def playwright(self) -> Optional[Playwright]:
        return self._pw

    def __get_launcher(self):
        if self._pw is None:
            raise RuntimeError("Playwright not initialized. Call start() first.")
        if self.config.browser_type == "firefox":
            return self._pw.firefox
        return self._pw.chromium

    def __get_channel(self) -> Optional[str]:
        if self.config.browser_type == "chrome":
            return "chrome"
        elif self.config.browser_type == "edge":
            return "msedge"
        return None
