"""Live2D 窗口内的**组件 UI 设置面板**（Qt，不对外暴露）。

107 个组件级设置按 8 个分组放进 Tab，编辑后写入
``ComponentSettingsStore`` 并立即回调热应用，**不走服务配置三态、
不写存档、不调用任何 HTTP API**。

5 个对外字段（model_path / canvas_size / fps / enable_audio_sync /
pipeface_model_path）不在这里出现，仍由 Web 设置页 ServiceConfig.vue 管。

面板本身可脱离服务独立创建，供 ``src/tests/test_live2d_ui.py`` 的
「创建视图」测试断言控件齐全。
"""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox,
    QVBoxLayout, QWidget, QTabWidget,
)

from .component_settings import ComponentSettingsStore
from .settings import component_specs, groups

ApplyCallback = Callable[[Dict[str, Any]], None]


class Live2DSettingsPanel(QDialog):
    """8 分组 / 107 项组件设置的可视化编辑器。"""

    def __init__(
        self,
        store: Optional[ComponentSettingsStore] = None,
        on_apply: Optional[ApplyCallback] = None,
        parent: Optional[QWidget] = None,
        public_cfg: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(parent)
        self.store = store or ComponentSettingsStore()
        self._on_apply = on_apply
        self._public = dict(public_cfg or {})
        self._widgets: Dict[str, QWidget] = {}
        self._specs = component_specs()
        self._group_names: List[str] = []
        self._applied: List[Dict[str, Any]] = []

        self.setWindowTitle("Live2D 组件设置")
        self.setObjectName("live2d_settings_panel")
        self.setMinimumSize(720, 560)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        root = QVBoxLayout(self)
        self._tabs = QTabWidget()
        self._tabs.setObjectName("live2d_settings_tabs")
        root.addWidget(self._tabs)

        self._build_tabs()
        self._build_footer(root)
        self.set_values(self.store.load())

    # ── 构建 ─────────────────────────────────────────────────────

    def _build_tabs(self) -> None:
        specs_by_key = {s["key"]: s for s in self._specs}
        for group in groups():
            if group["count"] == 0:
                continue
            self._group_names.append(group["name"])
            page = QWidget()
            page.setObjectName("settings_group")
            form = QFormLayout(page)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            for key in group["keys"]:
                spec = specs_by_key[key]
                widget = self._make_widget(spec)
                self._widgets[key] = widget
                label = QLabel(spec["label"])
                label.setToolTip(spec.get("description", "") or key)
                form.addRow(label, widget)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            self._tabs.addTab(scroll, group["name"])

    @staticmethod
    def _make_widget(spec: Dict[str, Any]) -> QWidget:
        t = spec["type"]
        default = spec["default"]
        if callable(default):
            default = default()
        if t == "boolean":
            w = QCheckBox()
            w.setChecked(bool(default))
            return w
        if t == "number":
            lo = spec.get("min", 0.0)
            hi = spec.get("max", 9999.0)
            if isinstance(default, int) and not isinstance(default, bool):
                w = QSpinBox()
                w.setRange(int(lo), int(hi))
                w.setValue(int(default))
            else:
                w = QDoubleSpinBox()
                w.setDecimals(3)
                w.setRange(float(lo), float(hi))
                w.setSingleStep(0.05 if float(hi) <= 3 else 1.0)
                w.setValue(float(default))
            return w
        if t == "object":
            w = QPlainTextEdit()
            w.setPlainText(json.dumps(default, ensure_ascii=False,
                                      indent=2, sort_keys=True))
            w.setMaximumHeight(96)
            return w
        if t == "password":
            w = QLineEdit(str(default))
            w.setEchoMode(QLineEdit.EchoMode.Password)
            return w
        if spec.get("options"):
            w = QComboBox()
            w.addItems([str(o) for o in spec["options"]])
            idx = w.findText(str(default))
            if idx >= 0:
                w.setCurrentIndex(idx)
            return w
        w = QLineEdit(str(default))
        return w

    def _build_footer(self, root: QVBoxLayout) -> None:
        hint = QLabel(
            "仅组件内部设置（107 项），保存到 <用户数据>/live2d/ui_settings.json；"
            "模型路径 / 画布尺寸 / 帧率 / 口型 / 人脸模型请在服务设置页修改。"
        )
        hint.setWordWrap(True)
        hint.setObjectName("settings_hint")
        root.addWidget(hint)

        row = QHBoxLayout()
        row.addStretch(1)
        self._btn_reset = QPushButton("恢复默认")
        self._btn_cancel = QPushButton("取消")
        self._btn_apply = QPushButton("应用")
        self._btn_apply.setDefault(True)
        self._btn_reset.clicked.connect(self._on_reset)
        self._btn_cancel.clicked.connect(self.reject)
        self._btn_apply.clicked.connect(self._on_apply_clicked)
        for b in (self._btn_reset, self._btn_cancel, self._btn_apply):
            row.addWidget(b)
        root.addLayout(row)

    # ── 值读写 ───────────────────────────────────────────────────

    def set_values(self, cfg: Dict[str, Any]) -> None:
        """程序化灌值（测试与「载入当前设置」用）。"""
        for key, w in self._widgets.items():
            if key not in cfg:
                continue
            value = cfg[key]
            if isinstance(w, QCheckBox):
                w.setChecked(bool(value))
            elif isinstance(w, QSpinBox):
                w.setValue(int(value))
            elif isinstance(w, QDoubleSpinBox):
                w.setValue(float(value))
            elif isinstance(w, QComboBox):
                idx = w.findText(str(value))
                if idx >= 0:
                    w.setCurrentIndex(idx)
            elif isinstance(w, QPlainTextEdit):
                if isinstance(value, (dict, list)):
                    w.setPlainText(json.dumps(value, ensure_ascii=False,
                                             indent=2, sort_keys=True))
                else:
                    w.setPlainText(str(value))
            elif isinstance(w, QLineEdit):
                w.setText(str(value))

    def values(self) -> Dict[str, Any]:
        """从控件收集组件设置（不含对外 5 项）。"""
        out: Dict[str, Any] = {}
        specs = {s["key"]: s for s in self._specs}
        for key, w in self._widgets.items():
            if isinstance(w, QCheckBox):
                out[key] = bool(w.isChecked())
            elif isinstance(w, QSpinBox):
                out[key] = int(w.value())
            elif isinstance(w, QDoubleSpinBox):
                out[key] = float(w.value())
            elif isinstance(w, QComboBox):
                out[key] = str(w.currentText())
            elif isinstance(w, QPlainTextEdit):
                text = w.toPlainText().strip()
                try:
                    parsed = json.loads(text)
                    out[key] = parsed if isinstance(parsed, dict) else {}
                except ValueError:
                    out[key] = specs[key]["default"]
            elif isinstance(w, QLineEdit):
                out[key] = str(w.text())
        return out

    # ── 动作 ─────────────────────────────────────────────────────

    def _on_reset(self) -> None:
        self.set_values(self.store.reset())

    def _on_apply_clicked(self) -> None:
        cfg = self.apply_settings()
        self._applied.append(cfg)
        self.accept()

    def apply_settings(self) -> Dict[str, Any]:
        """保存 + 立即热应用；返回完整 cfg（组件 + 对外 5 项）。"""
        component = self.store.save(self.values())
        # 合并时带上当前对外 5 项，避免面板把服务配置里的模型路径/帧率冲成默认值
        full = self.store.merge(self._public or self.store.public_view(component))
        if self._on_apply:
            try:
                self._on_apply(full)
            except Exception:
                # 面板不因回调异常崩掉；错误由 controller 记录
                pass
        return {**component, **full}

    # ── 自检辅助 ─────────────────────────────────────────────────

    @property
    def widget_count(self) -> int:
        return len(self._widgets)

    @property
    def group_names(self) -> List[str]:
        return list(self._group_names)

    @property
    def applied_history(self) -> List[Dict[str, Any]]:
        return list(self._applied)

    @property
    def keys(self) -> List[str]:
        return list(self._widgets.keys())


def open_live2d_settings(
    parent: Optional[QWidget] = None,
    store: Optional[ComponentSettingsStore] = None,
    on_apply: Optional[ApplyCallback] = None,
    public_cfg: Optional[Dict[str, Any]] = None,
) -> Live2DSettingsPanel:
    """创建（不阻塞）设置面板并 show；返回对象便于调用方/测试持有。"""
    panel = Live2DSettingsPanel(store=store, on_apply=on_apply,
                                parent=parent, public_cfg=public_cfg)
    panel.show()
    return panel


__all__ = ["Live2DSettingsPanel", "open_live2d_settings"]
