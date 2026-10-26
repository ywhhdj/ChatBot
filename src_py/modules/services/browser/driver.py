"""Playwright 浏览器实例生命周期管理。

三种模式：
  1. `launch()`              —— 启动全新浏览器
  2. `launch_persistent()`   —— 用用户 profile 启动
  3. `connect_cdp()`         —— 连接已运行的浏览器
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Optional, Literal

from ... import runtime
from ...logger import logger
from ...utils.file import read_text
from ..config import BrowserConfig

# try:  # playwright 是可选依赖，缺失时本模块仍可被导入
#     from playwright.async_api import (
#         async_playwright, Browser, BrowserContext, Page, Playwright,
#     )
#     _PLAYWRIGHT_OK = True
# except ImportError:  # pragma: no cover
#     _PLAYWRIGHT_OK = False
#     async_playwright = None  # type: ignore
#     Browser = BrowserContext = Page = Playwright = object  # type: ignore
from playwright.async_api import (
    async_playwright, Browser, BrowserContext, Page, Playwright,
)
_PLAYWRIGHT_OK = True

BrowserType = Literal["chrome", "edge", "firefox"]

DEFAULT_VIEWPORT: Dict[str, int] = {"width": 1280, "height": 800}

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# 各平台默认安装位置
_EXE_CANDIDATES = {
    "chrome": {
        "win32": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ],
        "darwin": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
        "linux": [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/snap/bin/chromium",
            "/usr/bin/chromium"
        ],
    },
    "edge": {
        "win32": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ],
        "darwin": ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"],
        "linux": [
            "/usr/bin/microsoft-edge",
            "/usr/bin/microsoft-edge-stable",
        ],
    },
    "firefox": {
        "win32": [r"C:\Program Files\Mozilla Firefox\firefox.exe"],
        "darwin": ["/Applications/Firefox.app/Contents/MacOS/firefox"],
        "linux": ["/usr/bin/firefox"],
    },
}


class BrowserDriver:
    """统一管理 Playwright 浏览器实例的生命周期。"""

    def __init__(
        self,
        browser_type: BrowserType | str = "chrome",
        profile_dir: Optional[str] = None,
        cdp_url: Optional[str] = None,
        user_agent: Optional[str] = None,
        user_data_dir: Optional[str] = None,
        headless: bool = True,
        viewport: Optional[Dict[str, int]] = None,
        proxy: Optional[str] = None,
    ):
        if browser_type not in ("chrome", "edge", "firefox"):
            raise ValueError(f"Invalid browser type: {browser_type}")

        self.config = BrowserConfig(
            enabled=True,
            browser_type=browser_type,  # type: ignore[arg-type]
            headless=headless,
            user_data_dir=user_data_dir or "",
            profile_name=profile_dir or "",
            cdp_url=cdp_url or "",
            viewport=viewport or dict(DEFAULT_VIEWPORT),
            user_agent=user_agent or DEFAULT_UA,
            proxy=proxy or "",
        )
        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    # ---------- 可执行文件 ----------

    def _get_default_exe_path(self) -> str:
        """S46：按平台找已安装的浏览器；找不到返回空串（用自带内核）。"""
        table = _EXE_CANDIDATES.get(self.config.browser_type, {})
        for key in (sys.platform, "linux"):
            for candidate in table.get(key, []):
                if Path(candidate).exists():
                    return candidate
        return ""

    def _build_args(self) -> list:
        vp = self.config.viewport or DEFAULT_VIEWPORT
        return [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            f"--window-size={vp.get('width', 1280)},{vp.get('height', 800)}",
            "--enable-unsafe-swiftshader",
            "--use-gl=swiftshader",
            "--ignore-gpu-blocklist",
        ]

    # ---------- 启动 ----------

    async def start_browser(self, headless: bool = False) -> Page:
        if not _PLAYWRIGHT_OK:
            raise RuntimeError("playwright 未安装，无法启动浏览器")

        self._pw = await async_playwright().start()
        exe_path = self._get_default_exe_path()
        # S47：channel 与 executable_path 不能同时给
        channel = None if exe_path else self._get_channel()
        vp = self.config.viewport or DEFAULT_VIEWPORT

        try:
            if self.config.cdp_url:
                self._browser = await self._get_launcher().connect_over_cdp(
                    self.config.cdp_url
                )
                self._context = (
                    self._browser.contexts[0]
                    if self._browser.contexts
                    else await self._browser.new_context()
                )
            elif self.config.profile_name:
                if not self.config.user_data_dir:
                    raise ValueError("持久化模式需要提供 user_data_dir")
                self._context = await self._get_launcher().launch_persistent_context(
                    user_data_dir=self.config.user_data_dir,
                    headless=headless,
                    viewport=vp,  # type: ignore[union-attr][arg-type]
                    user_agent=self.config.user_agent,
                    args=self._build_args(),
                    executable_path=exe_path or None,
                    channel=channel,
                    proxy=self._proxy_option(),  # type: ignore[union-attr][arg-type]
                )
                self._browser = self._context.browser
            else:
                self._browser = await self._get_launcher().launch(
                    headless=headless,
                    args=self._build_args(),
                    executable_path=exe_path or None,
                    channel=channel,
                    proxy=self._proxy_option(),  # type: ignore[union-attr][arg-type]
                )
                self._context = await self._browser.new_context(
                    viewport=vp,                # type: ignore[union-attr][arg-type]
                    user_agent=self.config.user_agent,
                )
        except Exception as e:
            logger.error(f"[BrowserDriver] 启动失败: {e}")
            await self.stop_browser()
            raise

        self._page = (
            self._context.pages[0]
            if self._context.pages
            else await self._context.new_page()
        )
        if self.config.viewport:
            try:
                await self._page.set_viewport_size(
                    vp["width"], vp["height"]  # type: ignore[union-attr][arg-type]
                )
            except Exception:
                pass

        logger.info(f"[BrowserDriver] 已启动 {self.config.browser_type}")
        return self._page

    def _proxy_option(self):
        proxy = (self.config.proxy or "").strip()
        if not proxy:
            return None
        return {"server": proxy}

    async def stop_browser(self) -> None:
        """S49：cdp 模式只停 playwright 进程，不关用户的浏览器。"""
        try:
            if self._context is not None and not self.config.cdp_url:
                await self._context.close()
            if self._browser is not None and not self.config.cdp_url:
                await self._browser.close()
            if self._pw is not None:
                await self._pw.stop()
        except Exception as e:
            logger.error(f"[BrowserDriver] 关闭异常: {e}")
        finally:
            self._pw = None
            self._browser = None
            self._context = None
            self._page = None
            logger.info("[BrowserDriver] 已停止")

    async def new_page(self) -> Page:
        if not self._context:
            raise RuntimeError("Browser not started. Call start() first.")
        return await self._context.new_page()

    # ---------- 反检测 ----------

    def _load_script(self, name: str) -> Optional[str]:
        """S45：dev 与打包后都拼到 scripts/ 下，不再把目录当文件读。"""
        if runtime.is_dev_mode():
            js_path = Path(__file__).parent / "scripts" / name
        else:
            js_path = runtime.RuntimePath.get_scripts_path(name)
        return read_text(js_path)

    async def inject_stealth(self, script_name: str = "stealth.js") -> bool:
        """注入反检测脚本。返回是否成功（失败时不再静默）。"""
        if self._context is None:
            # S51
            logger.warning("[BrowserDriver] context 未就绪，跳过反检测注入")
            return False

        try:
            stealth = self._load_script(script_name)
        except Exception as e:
            logger.error(f"[BrowserDriver] 读取 {script_name} 失败: {e}")
            return False

        if not stealth:
            logger.warning(f"[BrowserDriver] {script_name} 内容为空")
            return False

        try:
            await self._context.add_init_script(stealth)
        except Exception as e:
            logger.error(f"[BrowserDriver] 注入反检测脚本失败: {e}")
            return False

        logger.info("[BrowserDriver] 反检测脚本已注入")
        return True

    # ---------- 属性 ----------

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

    # ---------- 内部 ----------

    def _get_launcher(self):
        if self._pw is None:
            raise RuntimeError("Playwright not initialized. Call start() first.")
        if self.config.browser_type == "firefox":
            return self._pw.firefox
        return self._pw.chromium

    def _get_channel(self) -> Optional[str]:
        if self.config.browser_type == "chrome":
            return "chrome"
        if self.config.browser_type == "edge":
            return "msedge"
        return None