"""PPT 数据模型。

修复对应清单：K18 / K20 / K29

对齐官方设计：
  * 产出物是**原生可编辑**结构（文本框 / 表格 / 图表），不是图片贴片
  * 大纲与渲染分离：先结构化（方法类技能），再产出文件（产物类技能）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

LayoutType = Literal[
    "cover", "agenda", "section", "bullets", "two_column",
    "metrics", "quote", "table", "chart", "closing",
]

ChartType = Literal["bar", "column", "pie", "line"]


@dataclass
class ColorScheme:
    """配色。对齐 Kimi Slides 的 primary / secondary / background / accent。"""

    primary: str = "#1F3A93"
    secondary: str = "#2E86C1"
    accent: str = "#F39C12"
    background: str = "#FFFFFF"
    text: str = "#1B1F23"
    muted: str = "#6B7280"

    def to_dict(self) -> Dict[str, str]:
        return {
            "primary": self.primary,
            "secondary": self.secondary,
            "accent": self.accent,
            "background": self.background,
            "text": self.text,
            "muted": self.muted,
        }


@dataclass
class SlideSpec:
    """单页规格。

    `layout` 决定版式；`points` / `metrics` / `table` / `chart` 按版式各取所需。
    """

    layout: LayoutType = "bullets"
    title: str = ""
    subtitle: str = ""
    points: List[str] = field(default_factory=list)
    columns: List[Dict[str, Any]] = field(default_factory=list)
    metrics: List[Dict[str, Any]] = field(default_factory=list)
    quote: str = ""
    source: str = ""
    table: Optional[Dict[str, Any]] = None
    chart: Optional[Dict[str, Any]] = None
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "layout": self.layout,
            "title": self.title,
            "subtitle": self.subtitle,
            "points": self.points,
            "columns": self.columns,
            "metrics": self.metrics,
            "quote": self.quote,
            "source": self.source,
            "table": self.table,
            "chart": self.chart,
            "notes": self.notes,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "SlideSpec":
        return SlideSpec(
            layout=str(d.get("layout") or "bullets"),  # type: ignore[union-attr]
            title=str(d.get("title") or ""),
            subtitle=str(d.get("subtitle") or ""),
            points=[str(x) for x in (d.get("points") or [])],
            columns=list(d.get("columns") or []),
            metrics=list(d.get("metrics") or []),
            quote=str(d.get("quote") or ""),
            source=str(d.get("source") or ""),
            table=d.get("table"),
            chart=d.get("chart"),
            notes=str(d.get("notes") or ""),
        )


@dataclass
class DeckSpec:
    """整副演示文稿的规格（大纲产物）。"""

    title: str = ""
    subtitle: str = ""
    author: str = ""
    audience: str = ""
    slides: List[SlideSpec] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "author": self.author,
            "audience": self.audience,
            "slides": [s.to_dict() for s in self.slides],
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "DeckSpec":
        raw = d.get("slides") or []
        return DeckSpec(
            title=str(d.get("title") or ""),
            subtitle=str(d.get("subtitle") or ""),
            author=str(d.get("author") or ""),
            audience=str(d.get("audience") or ""),
            slides=[SlideSpec.from_dict(s) for s in raw if isinstance(s, dict)],
        )


@dataclass
class TemplateSpec:
    """模板规格：风格描述 + 配色 + 版式框架。"""

    id: str = ""
    name: str = ""
    description: str = ""
    scenario: str = ""
    colors: ColorScheme = field(default_factory=ColorScheme)
    font_title: str = "微软雅黑"
    font_body: str = "微软雅黑"
    title_size: int = 40
    body_size: int = 18
    cover_frame: str = "居中大标题 + 副标题 + 强调色分隔线"
    body_frame: str = "左上标题 + 下方要点区 + 右下页码"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "scenario": self.scenario,
            "colors": self.colors.to_dict(),
            "font_title": self.font_title,
            "font_body": self.font_body,
            "title_size": self.title_size,
            "body_size": self.body_size,
            "cover_frame": self.cover_frame,
            "body_frame": self.body_frame,
        }


@dataclass
class RenderResult:
    """渲染产物。**只讲产出了什么、放在哪里**（官方沟通策略）。"""

    ok: bool = False
    file_path: str = ""
    file_name: str = ""
    slide_count: int = 0
    template_id: str = ""
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "file_path": self.file_path,
            "file_name": self.file_name,
            "slide_count": self.slide_count,
            "template_id": self.template_id,
            "message": self.message,
        }

