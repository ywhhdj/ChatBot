from pathlib import Path

class WebMainWindow:
    def __init__(self, title: str):
        self.title = title
        self.web_view = None

    def _resolve_web_entry(self):
        from ..config import get_config
        config = get_config()
        env_url = config.web.resources_path
        from PyQt5.QtCore import QUrl
        if env_url:
            return QUrl(env_url)
        root = Path(__file__).resolve().parents[3]
        candidates = root / "ui" / "web" / "index.html"
        if candidates.exists():
            return QUrl.fromLocalFile(str(candidates))
        raise FileNotFoundError("Cannot find web entry. Build ui/web first or set WEB_URL.")

    def run(self):
        from PyQt5.QtWebEngineWidgets import QWebEngineView
        self.web_view = QWebEngineView()
        self.web_view.setWindowTitle(self.title)

        # 先设置 WebChannel，再加载页面
        page = self.web_view.page()
        if page:
            from .channel import API
            page.setWebChannel(API())

        self.web_view.load(self._resolve_web_entry())
        self.web_view.show()
        
        


