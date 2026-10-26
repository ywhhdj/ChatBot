"""PPT 模板服务（对齐 Kimi Slides 的预设风格 + Custom Style）。

修复对应清单：K19 / K30

官方做法：
  * 预设风格模板（战略咨询 / 市场营销 / 学术研究 等）
  * Custom Style：用户写"风格描述"——配色、字体字号、封面设计、正文框架
  * Free Style：无预设时按上传文件与指令自由发挥

这里提供 5 套预设 + 自定义覆盖，且**渐进加载**：
只有真正要用某套模板时才构造它的完整说明。
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from src_py.modules.runtime import RuntimePath
from src_py.modules.utils.file import yaml

from .models import ColorScheme, TemplateSpec

# --------------------------------------------------------------------------
# 预设模板库
# --------------------------------------------------------------------------

def _tpl(
    id_: str, 
    name: str, scenario: str, description: str,
    colors: ColorScheme, title_size: int = 40, body_size: int = 18,
    font_title: str = "微软雅黑", font_body: str = "微软雅黑",
    cover_frame: str = "", body_frame: str = "",
) -> TemplateSpec:
    return TemplateSpec(
        id=id_, name=name, scenario=scenario, description=description,
        colors=colors, font_title=font_title, font_body=font_body,
        title_size=title_size, body_size=body_size,
        cover_frame=cover_frame, body_frame=body_frame,
    )

def load_defaluts():
    path=RuntimePath.get_ppt_template_file_path(is_defaults=True)
    data=yaml.read_yaml(path)
    PRESET_TEMPLATES={}
    for id_, spec in data.items():
        PRESET_TEMPLATES[id_]=_tpl(
            **spec,
            id_=spec["id"],
            colors=ColorScheme(
                primary=spec["colors"]["primary"],
                secondary=spec["colors"]["secondary"],
                accent=spec["colors"]["accent"],
                background=spec["colors"]["background"],
                text=spec["colors"]["text"],
                muted=spec["colors"]["muted"],
            ),
        )
    return PRESET_TEMPLATES

DEFAULT_TEMPLATE_ID = "consulting"


class PptTemplateService:
    """模板库管理：预设 + 自定义。"""

    def __init__(self) -> None:
        self._custom: Dict[str, TemplateSpec] = {}
        self._lock = threading.RLock()
        self._defaults = load_defaluts()

    # ---------- 查询 ----------

    def list_templates(self) -> List[Dict[str, Any]]:
        with self._lock:
            items = [t.to_dict() for t in self._defaults.values()]
            items.extend(t.to_dict() for t in self._custom.values())
        return items

    def ids(self) -> List[str]:
        with self._lock:
            return list(self._defaults.keys()) + list(self._custom.keys())

    def get(self, template_id: str) -> Optional[TemplateSpec]:
        if not template_id:
            return None
        with self._lock:
            tpl = self._defaults.get(str(template_id))
            if tpl is not None:
                return tpl
            return self._custom.get(str(template_id))

    def resolve(
        self,
        template_id: Optional[str] = None,
        style: str = "",
        colors: Optional[Dict[str, str]] = None,
    ) -> TemplateSpec:
        """解析出最终模板。

        优先级：指定模板 > 默认模板；style / colors 作为覆盖
        （对齐官方 Custom Style + 自定义配色）。
        """
        base = self.get(template_id or "") or self.get(DEFAULT_TEMPLATE_ID)
        if base is None:
            base = self._defaults[DEFAULT_TEMPLATE_ID]

        # 自定义风格：以 custom 为底再套用自定义描述
        if style and not template_id:
            base = self.get("custom") or base

        tpl = TemplateSpec(**base.to_dict())
        tpl.colors = ColorScheme(**base.colors.to_dict())

        if style:
            tpl.description = f"{base.description}；自定义要求：{style}"
        if colors:
            known = {
                k: v for k, v in colors.items()
                if k in ("primary", "secondary", "accent",
                              "background", "text", "muted") and v
            }
            if known:
                tpl.colors = ColorScheme(**{**tpl.colors.to_dict(), **known})
        return tpl

    # ---------- 自定义 ----------

    def register_custom(self, spec: TemplateSpec) -> None:
        if not spec.id:
            raise ValueError("模板 id 必填")
        with self._lock:
            self._custom[str(spec.id)] = spec

    def register_custom_from_style(
        self,
        style: str,
        colors: Optional[Dict[str, str]] = None,
        name: str = "自定义风格",
        scenario: str = "",
    ) -> TemplateSpec:
        """按风格描述创建自定义模板（官方 Custom Style 的等价实现）。"""
        base = self._defaults[DEFAULT_TEMPLATE_ID]
        spec = TemplateSpec(
            id="custom",
            name=name,
            scenario=scenario or "自定义",
            description=style,
            colors=ColorScheme(**{
                **base.colors.to_dict(),
                **(colors or {}),
            }),
            font_title=base.font_title,
            font_body=base.font_body,
            title_size=base.title_size,
            body_size=base.body_size,
            cover_frame=base.cover_frame,
            body_frame=base.body_frame,
        )
        self.register_custom(spec)
        return spec

    def unregister_custom(self, template_id: str) -> None:
        with self._lock:
            self._custom.pop(str(template_id), None)


_template_service: Optional[PptTemplateService] = None
_tpl_lock = threading.Lock()


def get_template_service() -> PptTemplateService:
    global _template_service
    if _template_service is None:
        with _tpl_lock:
            if _template_service is None:
                _template_service = PptTemplateService()
    return _template_service
