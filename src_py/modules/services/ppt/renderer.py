"""PPT 渲染服务：DeckSpec + TemplateSpec → 原生可编辑 .pptx。

修复对应清单：K20 / K21 / K22

官方强调的三条在这里落地：
  * **产出真文件**：用 python-pptx 的文本框 / 表格 / 原生图表对象，
    绝不截图贴片 —— 生成的 PPTX 在 Office 里每个元素都能改
  * **产出物约定**：文件一律写到 `RuntimePath.get_output_dir()`
  * **交付可被程序取回**：返回绝对路径，前端可直接下载

依赖降级：python-pptx 缺失时 `available=False`，
调用时抛明确错误，不会在导入阶段炸。
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

from ...logger import logger
from ...runtime import RuntimePath
from .models import DeckSpec, RenderResult, SlideSpec, TemplateSpec

try:  # python-pptx 是可选依赖
    from pptx import Presentation
    from pptx.chart.data import CategoryChartData
    from pptx.dml.color import RGBColor
    from pptx.enum.chart import XL_CHART_TYPE
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Emu, Inches, Pt

    _PPTX_OK = True
except ImportError:  # pragma: no cover
    _PPTX_OK = False
    Presentation = None  # type: ignore

EMU_PER_INCH = 914400


def _rgb(hex_color: str, default: str = "000000") -> "RGBColor":
    """#RRGGBB → RGBColor。容错：缺 #、长度不对、非十六进制。"""
    s = (hex_color or "").strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", s):
        s = default
    return RGBColor(int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


class PptRenderService:
    """把结构化大纲渲染成 .pptx。"""

    def __init__(self, output_dir: Optional[str] = None) -> None:
        self._output_dir = output_dir

    @property
    def available(self) -> bool:
        return _PPTX_OK

    def output_dir(self) -> str:
        if self._output_dir:
            os.makedirs(self._output_dir, exist_ok=True)
            return self._output_dir
        return str(RuntimePath.get_output_dir())

    # ═══════════════════════════════════════════════════════
    #  主入口
    # ═══════════════════════════════════════════════════════

    def render(
        self,
        deck: DeckSpec,
        template: TemplateSpec,
        file_name: Optional[str] = None,
    ) -> RenderResult:
        if not _PPTX_OK:
            return RenderResult(ok=False, message="未安装 python-pptx：pip install python-pptx")

        import uuid

        name = file_name or f"ppt_{uuid.uuid4().hex[:12]}.pptx"
        if not name.endswith(".pptx"):
            name += ".pptx"
        # 防目录穿越
        name = os.path.basename(name)

        out_dir = self.output_dir()
        path = os.path.join(out_dir, name)

        try:
            prs = Presentation()
            prs.slide_width = Inches(13.333)
            prs.slide_height = Inches(7.5)
            blank = prs.slide_layouts[6]

            if not deck.slides:
                return RenderResult(ok=False, message="大纲为空，没有可渲染的页面")

            for idx, spec in enumerate(deck.slides):
                slide = prs.slides.add_slide(blank)
                self._draw(slide, spec, template, idx, len(deck.slides))

            prs.save(path)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[PPT] 渲染失败: {e}")
            return RenderResult(ok=False, message=f"渲染失败: {e}")

        return RenderResult(
            ok=True,
            file_path=path,
            file_name=name,
            slide_count=len(deck.slides),
            template_id=template.id,
            message=f"已生成 {len(deck.slides)} 页：{name}",
        )

    # ═══════════════════════════════════════════════════════
    #  版式分发
    # ═══════════════════════════════════════════════════════

    def _draw(
        self,
        slide,
        spec: SlideSpec,
        tpl: TemplateSpec,
        idx: int,
        total: int
    ) -> None:
        layout = (spec.layout or "bullets").lower()
        handler = {
            "cover": self._cover,
            "agenda": self._agenda,
            "section": self._section,
            "bullets": self._bullets,
            "two_column": self._two_column,
            "metrics": self._metrics,
            "quote": self._quote,
            "table": self._table,
            "chart": self._chart,
            "closing": self._closing,
        }.get(layout, self._bullets)

        self._background(slide, tpl)
        # K21：深色底模板用浅色文字，避免"白字白底"
        self._title(slide, spec, tpl, layout)
        handler(slide, spec, tpl)
        self._footer(slide, tpl, idx, total)

    # ---------- 通用元素 ----------

    def _background(self, slide, tpl: TemplateSpec) -> None:
        from pptx.util import Inches

        box = slide.shapes.add_textbox(Inches(0), Inches(0), Inches(13.333), Inches(7.5))
        box.fill.solid()
        box.fill.fore_color.rgb = _rgb(tpl.colors.background, "FFFFFF")
        box.line.fill.background()
        box.text_frame.text = ""

    def _title(self, slide, spec: SlideSpec, tpl: TemplateSpec, layout: str) -> None:
        from pptx.util import Inches, Pt

        if layout in ("cover", "section", "closing", "quote"):
            return  # 这几种版式自己画标题
        if not spec.title:
            return
        box = slide.shapes.add_textbox(Inches(0.6), Inches(0.45), Inches(12.1), Inches(1.0))
        tf = box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = spec.title
        p.font.size = Pt(tpl.title_size * 0.62)
        p.font.bold = True
        p.font.name = tpl.font_title
        p.font.color.rgb = _rgb(tpl.colors.primary)

        # 标题下分隔线
        line = slide.shapes.add_textbox(Inches(0.6), Inches(1.35), Inches(11.5), Inches(0.05))
        line.fill.solid()
        line.fill.fore_color.rgb = _rgb(tpl.colors.accent)
        line.line.fill.background()
        line.text_frame.text = ""

    def _footer(self, slide, tpl: TemplateSpec, idx: int, total: int) -> None:
        from pptx.util import Inches, Pt

        box = slide.shapes.add_textbox(Inches(11.6), Inches(7.0), Inches(1.3), Inches(0.4))
        p = box.text_frame.paragraphs[0]
        p.text = f"{idx + 1} / {total}"
        p.font.size = Pt(10)
        p.font.name = tpl.font_body
        p.font.color.rgb = _rgb(tpl.colors.muted, "6B7280")

    def _text(self, slide, text: str, left: float, top: float,
              width: float, height: float, tpl: TemplateSpec,
              size: int = 18, bold: bool = False,
              color: Optional[str] = None, align: str = "left") -> None:
        from pptx.util import Inches, Pt

        box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
        tf = box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = text
        p.font.size = Pt(size)
        p.font.bold = bold
        p.font.name = tpl.font_body
        p.font.color.rgb = _rgb(color or tpl.colors.text)
        p.alignment = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER,
                       "right": PP_ALIGN.RIGHT}.get(align, PP_ALIGN.LEFT)
        return box

    def _bullets_block(self, slide, points: List[str], tpl: TemplateSpec,
                       left: float, top: float, width: float) -> None:
        from pptx.util import Inches, Pt

        box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(4.6))
        tf = box.text_frame
        tf.word_wrap = True
        first = True
        for item in points[:5]:
            p = tf.paragraphs[0] if first else tf.add_paragraph()
            first = False
            p.text = f"• {item}"
            p.font.size = Pt(tpl.body_size)
            p.font.name = tpl.font_body
            p.font.color.rgb = _rgb(tpl.colors.text)
            p.space_after = Pt(10)

    # ---------- 各版式 ----------

    def _cover(self, slide, spec: SlideSpec, tpl: TemplateSpec) -> None:
        from pptx.util import Inches, Pt

        accent = slide.shapes.add_textbox(Inches(0), Inches(0), Inches(13.333), Inches(0.18))
        accent.fill.solid()
        accent.fill.fore_color.rgb = _rgb(tpl.colors.accent)
        accent.line.fill.background()
        accent.text_frame.text = ""

        self._text(slide, spec.title or "演示标题", 1.0, 2.5, 11.3, 1.6,
                   tpl, size=tpl.title_size, bold=True,
                   color=tpl.colors.primary, align="center")
        if spec.subtitle:
            self._text(slide, spec.subtitle, 1.0, 4.2, 11.3, 0.8,
                       tpl, size=tpl.body_size + 4,
                       color=tpl.colors.muted, align="center")
        line = slide.shapes.add_textbox(Inches(5.6), Inches(5.1), Inches(2.1), Inches(0.06))
        line.fill.solid()
        line.fill.fore_color.rgb = _rgb(tpl.colors.secondary)
        line.line.fill.background()
        line.text_frame.text = ""
        if spec.source:
            self._text(slide, spec.source, 1.0, 5.5, 11.3, 0.5,
                       tpl, size=12, color=tpl.colors.muted, align="center")

    def _agenda(self, slide, spec: SlideSpec, tpl: TemplateSpec) -> None:
        items = spec.points or [c.get("title", "") for c in spec.columns]
        self._bullets_block(slide, [f"{i + 1}. {x}" for i, x in enumerate(items[:6])],
                            tpl, 1.0, 1.8, 11.0)

    def _section(self, slide, spec: SlideSpec, tpl: TemplateSpec) -> None:
        from pptx.util import Inches, Pt

        num = slide.shapes.add_textbox(Inches(1.0), Inches(2.4), Inches(2.0), Inches(1.4))
        p = num.text_frame.paragraphs[0]
        p.text = (spec.subtitle or "01").upper()
        p.font.size = Pt(72)
        p.font.bold = True
        p.font.name = tpl.font_title
        p.font.color.rgb = _rgb(tpl.colors.accent)

        self._text(slide, spec.title or "章节", 3.2, 2.9, 9.0, 1.0,
                   tpl, size=tpl.title_size, bold=True, color=tpl.colors.primary)

    def _bullets(self, slide, spec: SlideSpec, tpl: TemplateSpec) -> None:
        if spec.subtitle:
            self._text(slide, spec.subtitle, 0.7, 1.5, 11.8, 0.5,
                       tpl, size=tpl.body_size, color=tpl.colors.secondary)
        self._bullets_block(slide, spec.points, tpl, 0.9, 2.0, 11.5)
        if spec.source:
            self._text(
                slide,
                f"来源：{spec.source}",
                0.9, 6.4, 11.0, 0.4,
                tpl,
                size=11,
                color=tpl.colors.muted
            )

    def _two_column(self, slide, spec: SlideSpec, tpl: TemplateSpec) -> None:
        cols = spec.columns[:2] or [{"title": "", "points": spec.points[:3]},
                                    {"title": "", "points": spec.points[3:]}]
        for i, col in enumerate(cols):
            left = 0.9 + i * 6.0
            title = col.get("title") or ""
            if title:
                self._text(slide, title, left, 1.9, 5.4, 0.5,
                           tpl, size=tpl.body_size + 2, bold=True,
                           color=tpl.colors.secondary)
            self._bullets_block(slide, list(col.get("points") or [])[:5],
                                tpl, left, 2.6, 5.4)

    def _metrics(self, slide, spec: SlideSpec, tpl: TemplateSpec) -> None:
        from pptx.util import Inches, Pt

        items = spec.metrics[:4]
        if not items:
            self._bullets_block(slide, spec.points, tpl, 0.9, 2.0, 11.5)
            return
        width = 11.6 / max(len(items), 1)
        for i, m in enumerate(items):
            left = 0.9 + i * width
            card = slide.shapes.add_textbox(Inches(left), Inches(2.0),
                                            Inches(width - 0.3), Inches(2.6))
            card.fill.solid()
            card.fill.fore_color.rgb = _rgb(tpl.colors.background, "FFFFFF")
            card.line.color.rgb = _rgb(tpl.colors.secondary)
            tf = card.text_frame
            tf.word_wrap = True
            value = f"{m.get('value', '')}{m.get('unit', '')}"
            p = tf.paragraphs[0]
            p.text = value
            p.font.size = Pt(40)
            p.font.bold = True
            p.font.name = tpl.font_title
            p.font.color.rgb = _rgb(tpl.colors.primary)
            p.alignment = PP_ALIGN.CENTER
            p2 = tf.add_paragraph()
            p2.text = str(m.get("label", ""))
            p2.font.size = Pt(tpl.body_size)
            p2.font.name = tpl.font_body
            p2.font.color.rgb = _rgb(tpl.colors.muted)
            p2.alignment = PP_ALIGN.CENTER

    def _quote(self, slide, spec: SlideSpec, tpl: TemplateSpec) -> None:
        from pptx.util import Pt

        text = spec.quote or (spec.points[0] if spec.points else spec.title)
        box = self._text(slide, f"“{text}”", 1.4, 2.4, 10.5, 2.4,
                         tpl, size=28, color=tpl.colors.primary, align="center")
        box.text_frame.paragraphs[0].font.italic = True
        if spec.source:
            self._text(slide, f"— {spec.source}", 1.4, 5.0, 10.5, 0.5,
                       tpl, size=14, color=tpl.colors.muted, align="center")

    def _table(self, slide, spec: SlideSpec, tpl: TemplateSpec) -> None:
        from pptx.util import Inches

        table_spec = spec.table or {}
        headers = list(table_spec.get("headers") or [])
        rows = list(table_spec.get("rows") or [])
        if not headers and not rows:
            self._bullets_block(slide, spec.points, tpl, 0.9, 2.0, 11.5)
            return

        n_rows = len(rows) + 1
        n_cols = max(len(headers), *(len(r) for r in rows)) if rows else len(headers)
        n_cols = max(n_cols, 1)
        shape = slide.shapes.add_table(
            n_rows, n_cols, Inches(0.9), Inches(1.9), Inches(11.5), Inches(4.4)
        )
        tbl = shape.table
        for c, h in enumerate(headers[:n_cols]):
            cell = tbl.cell(0, c)
            cell.text = str(h)
            para = cell.text_frame.paragraphs[0]
            para.font.size = Pt(tpl.body_size)
            para.font.bold = True
            para.font.name = tpl.font_body
            para.font.color.rgb = _rgb(tpl.colors.background, "FFFFFF")
            cell.fill.solid()
            cell.fill.fore_color.rgb = _rgb(tpl.colors.primary)
        for r, row in enumerate(rows, start=1):
            for c in range(n_cols):
                cell = tbl.cell(r, c)
                cell.text = str(row[c]) if c < len(row) else ""
                para = cell.text_frame.paragraphs[0]
                para.font.size = Pt(tpl.body_size - 2)
                para.font.name = tpl.font_body

    def _chart(self, slide, spec: SlideSpec, tpl: TemplateSpec) -> None:
        from pptx.util import Inches

        chart_spec = spec.chart or {}
        categories = list(chart_spec.get("categories") or [])
        series = list(chart_spec.get("series") or [])
        if not categories or not series:
            self._bullets_block(slide, spec.points, tpl, 0.9, 2.0, 11.5)
            return

        data = CategoryChartData()
        data.categories = [str(c) for c in categories]
        for s in series[:4]:
            data.add_series(
                str(s.get("name") or "系列"),
                [float(v) for v in (s.get("values") or [])]
            )

        ctype = str(chart_spec.get("type") or "column").lower()
        xl = {
            "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
            "bar": XL_CHART_TYPE.BAR_CLUSTERED,
            "line": XL_CHART_TYPE.LINE,
            "pie": XL_CHART_TYPE.PIE,
        }.get(ctype, XL_CHART_TYPE.COLUMN_CLUSTERED)

        # K21：原生图表对象，不是截图
        slide.shapes.add_chart(
            xl, Inches(1.2), Inches(1.9), Inches(10.9), Inches(4.6), data
        )

    def _closing(self, slide, spec: SlideSpec, tpl: TemplateSpec) -> None:
        from pptx.util import Pt

        text = spec.title or "谢谢"
        self._text(slide, text, 1.0, 2.9, 11.3, 1.4,
                   tpl, size=tpl.title_size + 8, bold=True,
                   color=tpl.colors.primary, align="center")
        if spec.subtitle:
            self._text(slide, spec.subtitle, 1.0, 4.4, 11.3, 0.8,
                       tpl, size=tpl.body_size + 2,
                       color=tpl.colors.muted, align="center")

    # ---------- 读取（校验产物） ----------

    def inspect(self, file_path: str) -> Dict[str, Any]:
        """读回一个 pptx，返回页数与元素统计（用于验证"真可编辑"）。"""
        if not _PPTX_OK:
            return {
                "ok": False,
                "message": "未安装 python-pptx"
            }
        if not os.path.exists(file_path):
            return {
                "ok": False,
                "message": "文件不存在"
            }
        try:
            prs = Presentation(file_path)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": str(e)}

        texts = tables = charts = pictures = 0
        for s in prs.slides:
            for sh in s.shapes:
                if sh.has_text_frame and sh.text_frame.text.strip():
                    texts += 1
                if getattr(sh, "has_table", False) and sh.has_table:
                    tables += 1
                if getattr(sh, "has_chart", False) and sh.has_chart:
                    charts += 1
                if sh.shape_type == 13:  # MSO_SHAPE_TYPE.PICTURE
                    pictures += 1
        return {
            "ok": True,
            "slides": len(prs.slides),
            "text_boxes": texts,
            "tables": tables,
            "charts": charts,
            "pictures": pictures,
        }
