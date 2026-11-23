"""Live2D / Galgame **组件内部设置**的单一权威源（不对外暴露）。

配置的归属（本轮按用户要求重新划线）
──────────────────────────────────────
* **对外契约 = 5 个字段，保持基线原样**：``model_path`` / ``canvas_size`` /
  ``fps`` / ``enable_audio_sync`` / ``pipeface_model_path``。它们由
  ``services/config.py::Live2DConfig.fields`` 声明，走服务配置三态
  （``get_config`` 保存 / ``apply_config`` 应用）、进存档 ``server`` section、
  由 Web 设置页 ``ServiceConfig.vue`` 渲染。**不增不减。**
* **其余 107 项全是组件 UI 设置**：视线、待机演出、表情动作、口型、动捕、
  性能、Galgame 对话框样式……只在这里定义，由 Live2D 窗口内的
  ``Live2DSettingsPanel`` 编辑，存到
  ``<user_data>/live2d/ui_settings.json``（``component_settings.py``），
  **不进服务配置、不进存档、不注册任何对外 API**。

这样「对外配置」保持最小且稳定，组件想加多少表现开关都不用改契约、
不用改存档格式、不用同步前端 service。``normalize()`` 仍把两层合并成一份
完整 cfg 交给行为内核，组件读到的永远是补齐过、夹紧过的字典。

历史坑（仍由本文件兜底）：原 ``views.py`` 往实例动态塞
``is_face_detected`` / ``media_pipe_face_model_path``，``to_dict()`` 只遍历
``fields`` 会丢字段、``apply_config`` 恢复后 AttributeError。
"""
from __future__ import annotations

from typing import Any, Dict, List

from ... import runtime

# 分组名只用于前端把一长串设置折叠成几个 section，不参与序列化
GROUP_MODEL = "模型与窗口"
GROUP_RENDER = "渲染与性能"
GROUP_GAZE = "视线（无动捕时跟随鼠标）"
GROUP_IDLE = "待机与表情"
GROUP_MOTION = "动作与情绪"
GROUP_AUDIO = "语音与口型"
GROUP_FACE = "动捕"
GROUP_DIALOGUE = "Galgame 对话框"

DEFAULT_EXPRESSION_WEIGHTS: Dict[str, float] = {
    "normal": 4.0,
    "smile": 2.0,
    "surprised": 1.0,
    "relaxed": 2.0,
}

DEFAULT_EMOTION_MAP: Dict[str, str] = {
    "neutral": "normal",
    "happy": "smile",
    "sad": "sad",
    "angry": "angry",
    "surprised": "surprised",
    "shy": "blush",
}


def _default_model_path() -> str:
    return str(runtime.RuntimePath.get_models_path(
        "live2d/肥牛/hiyori_pro_mic.model3.json"))


def _default_face_model_path() -> str:
    return str(runtime.RuntimePath.get_models_path(
        "mediapipe/face_landmarker.task"))


def S(
    key: str,
    label: str,
    type_: str = "string",
    default: Any = "",
    description: str = "",
    group: str = GROUP_MODEL,
    options: List[str] | None = None,
    min_: float | None = None,
    max_: float | None = None,
    **extra: Any,
) -> Dict[str, Any]:
    """一条设置的描述；会被转成 ``config._field`` 兼容的字典。"""
    item: Dict[str, Any] = {
        "key": key,
        "label": label,
        "type": type_,
        "default": default,
        "description": description,
        "options": options,
        "group": group,
    }
    if min_ is not None:
        item["min"] = min_
    if max_ is not None:
        item["max"] = max_
    item.update(extra)
    return item


# fmt: off
SETTINGS: List[Dict[str, Any]] = [
    # ── 模型与窗口 ────────────────────────────────────────────────
    S("model_path", "模型路径", default=_default_model_path,
      description=".model3.json 路径；热切换时渲染线程重新载入"),
    S("canvas_size", "画布尺寸", default="1200x800",
      description="宽x高；改变后渲染目标与 FBO 同步重建"),
    S("window_title", "窗口标题", default="Live2DModel"),
    S("window_icon_path", "窗口图标", default=""),
    S("always_on_top", "窗口置顶", "boolean", True),
    S("click_through", "点击穿透", "boolean", False,
      description="开启后鼠标事件穿透窗口；与拖拽/命中测试互斥"),
    S("frameless", "无边框", "boolean", True),
    S("window_x", "窗口 X", "number", -1, "留 -1 自动停靠右下角"),
    S("window_y", "窗口 Y", "number", -1, "留 -1 自动停靠右下角"),
    S("scale", "模型缩放", "number", 1.0, "0.2~3.0", min_=0.2, max_=3.0),
    S("offset_x", "水平偏移", "number", 0.0),
    S("offset_y", "垂直偏移", "number", 0.0),
    S("rotation", "旋转角度", "number", 0.0, "0~360", min_=0.0, max_=360.0),
    S("opacity", "整体不透明度", "number", 1.0, "0~1", min_=0.0, max_=1.0),
    S("auto_hide_seconds", "无操作自动淡出(秒)", "number", 0.0,
      "0=关闭；鼠标/对话有活动时自动恢复"),

    # ── 渲染与性能 ────────────────────────────────────────────────
    S("fps", "活动帧率", "number", 60, "", GROUP_RENDER, min_=1, max_=144),
    S("idle_fps", "空闲降帧", "number", 30,
      "无语音/无交互时降到该帧率省 GPU", GROUP_RENDER, min_=1, max_=144),
    S("adaptive_fps", "性能自适应", "boolean", True,
      "连续掉帧时自动降低 render_scale，恢复后回升", GROUP_RENDER),
    S("render_scale", "渲染分辨率倍率", "number", 1.0,
      "0.5 表示半分辨率离屏渲染再放大，显存/带宽降约 75%",
      GROUP_RENDER, min_=0.4, max_=1.0),
    S("min_render_scale", "自适应下限", "number", 0.6,
      "", GROUP_RENDER, min_=0.4, max_=1.0),
    S("frame_skip_on_hidden", "隐藏时暂停渲染", "boolean", True,
      "窗口 hide/minimize 时停帧，不再每帧 toImage", GROUP_RENDER),
    S("enable_stats", "采集性能统计", "boolean", True, "", GROUP_RENDER),
    S("stats_window_size", "统计滑动窗口", "number", 120,
      "", GROUP_RENDER, min_=10, max_=1000),

    # ── 视线 ──────────────────────────────────────────────────────
    S("gaze_enabled", "启用视线跟随", "boolean", True, "", GROUP_GAZE),
    S("gaze_when_no_face", "无动捕时跟随鼠标", "boolean", True,
      "核心开关：动捕未启用/无数据/超时后，改用鼠标位置驱动 ParamAngleX/Y 与 ParamEyeBallX/Y",
      GROUP_GAZE),
    S("gaze_sensitivity", "鼠标灵敏度", "number", 1.0,
      "", GROUP_GAZE, min_=0.1, max_=3.0),
    S("gaze_max_x", "水平最大角度(0~1)", "number", 1.0,
      "映射 ParamAngleX 的最大绝对值", GROUP_GAZE, min_=0.0, max_=1.0),
    S("gaze_max_y", "垂直最大角度(0~1)", "number", 0.7,
      "", GROUP_GAZE, min_=0.0, max_=1.0),
    S("gaze_eyeball", "眼球跟随强度", "number", 0.65,
      "额外驱动 ParamEyeBallX/Y，让眼睛比头转得更多（galgame 感）",
      GROUP_GAZE, min_=0.0, max_=1.0),
    S("gaze_smoothing", "平滑系数", "number", 0.18,
      "每帧向目标插值的比例，越小越柔", GROUP_GAZE, min_=0.01, max_=1.0),
    S("gaze_dead_zone", "中心死区", "number", 0.03,
      "", GROUP_GAZE, min_=0.0, max_=0.5),
    S("gaze_idle_drift", "空闲视线游离", "boolean", True,
      "长时间不动鼠标时轻微随机偏移，避免僵住", GROUP_GAZE),
    S("gaze_drift_interval", "游离间隔(秒)", "number", 3.2,
      "", GROUP_GAZE, min_=0.5, max_=30.0),
    S("gaze_drift_amount", "游离幅度", "number", 0.22,
      "", GROUP_GAZE, min_=0.0, max_=1.0),
    S("gaze_return_seconds", "鼠标离开回中(秒)", "number", 1.2,
      "", GROUP_GAZE, min_=0.0, max_=10.0),
    S("face_priority", "动捕数据优先", "boolean", True,
      "有新鲜动捕数据时冻结鼠标视线", GROUP_GAZE),
    S("face_timeout_ms", "动捕数据超时(毫秒)", "number", 800,
      "超过该时间没收到人脸数据即回落到鼠标", GROUP_GAZE, min_=100, max_=10000),

    # ── 待机与表情 ────────────────────────────────────────────────
    S("idle_enabled", "启用待机演出", "boolean", True, "", GROUP_IDLE),
    S("idle_after_seconds", "进入待机(秒)", "number", 5.0,
      "最后一次说话/点击/鼠标移动后计时", GROUP_IDLE, min_=0.5, max_=120.0),
    S("idle_min_interval", "演出最小间隔(秒)", "number", 4.0,
      "", GROUP_IDLE, min_=0.5, max_=120.0),
    S("idle_max_interval", "演出最大间隔(秒)", "number", 12.0,
      "", GROUP_IDLE, min_=0.5, max_=300.0),
    S("idle_expression_weights", "随机表情权重", "object",
      DEFAULT_EXPRESSION_WEIGHTS,
      "表情 id → 权重；id 必须存在于模型的 .model3.json，留空则只做动作",
      GROUP_IDLE),
    S("idle_motion_group", "待机动作组", "string", "Idle",
      "", GROUP_IDLE),
    S("idle_motion_priority", "待机动作优先级", "number", 1,
      "0=NONE 1=IDLE 2=NORMAL 3=FORCE", GROUP_IDLE, min_=0, max_=3),
    S("idle_blink", "待机随机眨眼", "boolean", True,
      "与模型自带自动眨眼叠加时建议关掉 auto_blink", GROUP_IDLE),
    S("idle_blink_interval", "眨眼间隔(秒)", "number", 4.5,
      "", GROUP_IDLE, min_=0.5, max_=30.0),
    S("idle_head_sway", "待机轻微歪头", "boolean", True,
      "给 ParamAngleZ 一个缓慢正弦扰动", GROUP_IDLE),
    S("idle_pause_on_speaking", "说话时暂停演出", "boolean", True,
      "", GROUP_IDLE),
    S("idle_pause_on_face", "动捕时暂停演出", "boolean", True,
      "", GROUP_IDLE),
    S("auto_blink", "模型自动眨眼", "boolean", True, "", GROUP_IDLE),
    S("auto_breath", "模型自动呼吸", "boolean", True, "", GROUP_IDLE),

    # ── 动作与情绪 ────────────────────────────────────────────────
    S("speak_expression", "说话表情", "string", "",
      "TTS 开始时切换的表情 id；空=不切换", GROUP_MOTION),
    S("speak_motion_group", "说话动作组", "string", "Speak",
      "", GROUP_MOTION),
    S("emotion_map", "情绪→表情映射", "object", DEFAULT_EMOTION_MAP,
      "pipeline 输出的情绪名 → 模型表情 id", GROUP_MOTION),
    S("click_motion_group", "点击动作组", "string", "Tap",
      "命中模型部件时播放", GROUP_MOTION),
    S("hit_test_enabled", "启用部件命中", "boolean", True,
      "", GROUP_MOTION),
    S("hit_feedback_enabled", "命中高亮反馈", "boolean", False,
      "默认关闭：原实现会改部件乘色且不还原", GROUP_MOTION),
    S("double_click_expression", "双击表情", "string", "",
      "", GROUP_MOTION),
    S("drag_enabled", "允许拖拽窗口", "boolean", True,
      "关闭后左键只用于命中测试", GROUP_MOTION),

    # ── 语音与口型 ────────────────────────────────────────────────
    S("enable_audio_sync", "流式口型同步", "boolean", False,
      "用 TTS 音频块 RMS 驱动，需 enable_chunk_playback 配合",
      GROUP_AUDIO),
    S("enable_chunk_playback", "分块播放", "boolean", False,
      "", GROUP_AUDIO),
    S("audio_sample_rate", "采样率", "number", 44100, "", GROUP_AUDIO),
    S("audio_channels", "声道数", "number", 1, "", GROUP_AUDIO),
    S("audio_sample_width", "采样位宽(字节)", "number", 2,
      "仅支持 16-bit PCM(2)", GROUP_AUDIO),
    S("lip_sync_gain", "口型增益", "number", 3.0,
      "", GROUP_AUDIO, min_=0.0, max_=10.0),
    S("lip_sync_smoothing", "口型平滑", "number", 0.35,
      "避免 RMS 抖动导致嘴巴抽搐", GROUP_AUDIO, min_=0.0, max_=1.0),
    S("lip_sync_decay", "静音回落速度", "number", 0.25,
      "每帧向 0 收敛的比例", GROUP_AUDIO, min_=0.01, max_=1.0),

    # ── 动捕 ──────────────────────────────────────────────────────
    S("is_face_detected", "启用人脸动捕", "boolean", False,
      "关闭/无数据时自动走「视线跟随鼠标」", GROUP_FACE),
    S("pipeface_model_path", "人脸模型路径", default=_default_face_model_path,
      group=GROUP_FACE),
    S("face_source", "摄像头源", "string", "0",
      "设备序号或视频路径", GROUP_FACE),
    S("face_fps", "动捕帧率", "number", 30, "", GROUP_FACE, min_=1, max_=60),
    S("face_mirror", "镜像", "boolean", False, "", GROUP_FACE),
    S("face_smoothing", "动捕平滑", "number", 0.45,
      "", GROUP_FACE, min_=0.0, max_=1.0),

    # ── Galgame 对话框 ────────────────────────────────────────────
    S("dialogue_enabled", "启用对话框", "boolean", True,
      "", GROUP_DIALOGUE),
    S("dialogue_position", "位置", "string", "bottom",
      "", GROUP_DIALOGUE, options=["bottom", "top", "custom"]),
    S("dialogue_anchor_x", "自定义 X", "number", 0,
      "position=custom 时生效", GROUP_DIALOGUE),
    S("dialogue_anchor_y", "自定义 Y", "number", 0,
      "", GROUP_DIALOGUE),
    S("dialogue_max_width", "最大宽度", "number", 1000,
      "", GROUP_DIALOGUE, min_=320, max_=3840),
    S("dialogue_height", "高度", "number", 200,
      "", GROUP_DIALOGUE, min_=100, max_=800),
    S("dialogue_typing_cps", "打字速度(字/秒)", "number", 30,
      "", GROUP_DIALOGUE, min_=1, max_=120),
    S("dialogue_batch_size", "每帧字数", "number", 1,
      "", GROUP_DIALOGUE, min_=1, max_=20),
    S("dialogue_punctuation_pause_ms", "标点停顿(毫秒)", "number", 180,
      "，。！？… 后额外停顿，galgame 的节奏感", GROUP_DIALOGUE,
      min_=0, max_=2000),
    S("dialogue_instant", "默认瞬时显示", "boolean", False,
      "", GROUP_DIALOGUE),
    S("dialogue_auto_seconds", "自动推进(秒)", "number", 0.0,
      "0=关闭；读完文本后自动 advance", GROUP_DIALOGUE, min_=0.0, max_=60.0),
    S("dialogue_queue_mode", "多段文本策略", "string", "interrupt",
      "", GROUP_DIALOGUE, options=["interrupt", "queue"]),
    S("dialogue_click_to_advance", "点击推进/跳过", "boolean", True,
      "", GROUP_DIALOGUE),
    S("dialogue_skip_read", "跳过已读文本", "boolean", True,
      "Ctrl 按住时跳过已读", GROUP_DIALOGUE),
    S("dialogue_backlog_size", "回看条数", "number", 100,
      "", GROUP_DIALOGUE, min_=0, max_=1000),
    S("dialogue_name_visible", "显示说话人", "boolean", True,
      "", GROUP_DIALOGUE),
    S("dialogue_name_color", "说话人颜色", "string", "#FFD9A0",
      "", GROUP_DIALOGUE),
    S("dialogue_name_font_size", "说话人字号", "number", 15,
      "", GROUP_DIALOGUE, min_=8, max_=48),
    S("dialogue_text_color", "正文颜色", "string", "#F5F0E6",
      "", GROUP_DIALOGUE),
    S("dialogue_font_family", "字体", "string", "Microsoft YaHei",
      "", GROUP_DIALOGUE),
    S("dialogue_font_size", "正文字号", "number", 17,
      "", GROUP_DIALOGUE, min_=8, max_=48),
    S("dialogue_line_spacing", "行距", "number", 1.55,
      "", GROUP_DIALOGUE, min_=1.0, max_=3.0),
    S("dialogue_bg_color", "背景颜色", "string", "#0B0B14",
      "", GROUP_DIALOGUE),
    S("dialogue_bg_opacity", "背景不透明度", "number", 0.82,
      "", GROUP_DIALOGUE, min_=0.0, max_=1.0),
    S("dialogue_border_radius", "圆角", "number", 14,
      "", GROUP_DIALOGUE, min_=0, max_=60),
    S("dialogue_border_color", "边框颜色", "string", "#D9C7A7",
      "", GROUP_DIALOGUE),
    S("dialogue_border_width", "边框宽度", "number", 1,
      "", GROUP_DIALOGUE, min_=0, max_=10),
    S("dialogue_padding", "内边距", "number", 18,
      "", GROUP_DIALOGUE, min_=0, max_=80),
    S("dialogue_shadow", "文字阴影", "boolean", True,
      "半透明底上保证可读", GROUP_DIALOGUE),
    S("dialogue_outline", "文字描边", "boolean", True,
      "", GROUP_DIALOGUE),
    S("dialogue_outline_color", "描边颜色", "string", "#1A1420",
      "", GROUP_DIALOGUE),
    S("dialogue_word_wrap", "自动换行", "boolean", True,
      "", GROUP_DIALOGUE),
    S("dialogue_text_align", "对齐", "string", "left",
      "", GROUP_DIALOGUE, options=["left", "center", "right"]),
    S("dialogue_indicator_visible", "显示等待指示器", "boolean", True,
      "读完显示闪烁 ▼", GROUP_DIALOGUE),
    S("dialogue_draggable", "可拖拽", "boolean", True,
      "", GROUP_DIALOGUE),
    S("dialogue_on_top", "置顶", "boolean", True,
      "", GROUP_DIALOGUE),
    S("dialogue_fade_ms", "淡入淡出(毫秒)", "number", 160,
      "", GROUP_DIALOGUE, min_=0, max_=2000),
    S("dialogue_typewriter_sound", "逐字音效", "boolean", False,
      "仅发信号，由外部绑定音频", GROUP_DIALOGUE),
    S("dialogue_emotion_sync", "联动模型表情", "boolean", True,
      "说话开始切 speak_expression，结束恢复", GROUP_DIALOGUE),
]
# fmt: on

DEFAULTS: Dict[str, Any] = {
    s["key"]: (s["default"]() if callable(s["default"]) else s["default"])
    for s in SETTINGS
}

_NUMERIC_RANGES: Dict[str, tuple[float | None, float | None]] = {
    s["key"]: (s.get("min"), s.get("max"))
    for s in SETTINGS if s["type"] == "number"
}


def build_fields() -> List[Dict[str, Any]]:
    """转成 ``BaseServiceConfig.fields`` 兼容格式（含 group 等 extra）。

    键名必须与 ``config._field()`` 一致：``type`` 而不是 ``type_``，
    否则 ``get_ui_config_items()`` 交给前端的字段会缺类型。
    """
    return [dict(s) for s in SETTINGS]


def normalize(raw: Dict[str, Any] | None) -> Dict[str, Any]:
    """把任意来源（存档 / API / UI）的配置规范化成完整、类型正确的字典。

    * 缺失键用默认值补齐 —— 老存档升级后不会 AttributeError；
    * 数值键做 min/max 夹紧，杜绝 ``fps=0`` 导致除零、``opacity=99`` 之类；
    * 旧别名 ``media_pipe_face_model_path`` / ``window_size`` 自动映射；
    * 未知键保留（前端新增字段不至于被吞），但不写进 ``DEFAULTS``。
    """
    out: Dict[str, Any] = {}
    for key, value in DEFAULTS.items():
        out[key] = _clone(value)
    src = dict(raw or {})
    # 旧版本动态属性的兼容映射
    if "media_pipe_face_model_path" in src and "pipeface_model_path" not in src:
        src["pipeface_model_path"] = src.pop("media_pipe_face_model_path")
    else:
        src.pop("media_pipe_face_model_path", None)
    if "window_size" in src and "canvas_size" not in src:
        ws = src.pop("window_size")
        if isinstance(ws, (list, tuple)) and len(ws) == 2:
            src["canvas_size"] = f"{int(ws[0])}x{int(ws[1])}"
    for key, value in src.items():
        if key == "service" or key == "name" or key == "enabled":
            continue
        out[key] = _coerce(key, value)
    return out


def _clone(value: Any) -> Any:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list):
        return list(value)
    return value


def _coerce(key: str, value: Any) -> Any:
    spec = next((s for s in SETTINGS if s["key"] == key), None)
    if spec is None:
        return value
    t = spec["type"]
    if t == "boolean":
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)
    if t == "number":
        try:
            num = float(value)
        except (TypeError, ValueError):
            return _clone(spec["default"])
        lo, hi = _NUMERIC_RANGES.get(key, (None, None))
        if lo is not None:
            num = max(lo, num)
        if hi is not None:
            num = min(hi, num)
        return int(num) if float(num).is_integer() and _is_int_spec(spec) else num
    if t == "object":
        if isinstance(value, str):
            import json
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else _clone(spec["default"])
            except ValueError:
                return _clone(spec["default"])
        return dict(value) if isinstance(value, dict) else _clone(spec["default"])
    return str(value)


def _is_int_spec(spec: Dict[str, Any]) -> bool:
    return isinstance(spec["default"], int) and not isinstance(spec["default"], bool)


def parse_canvas_size(value: Any) -> tuple[int, int]:
    """``"1200x800"`` / ``[1200, 800]`` / ``{"width":..}`` → (w, h)。"""
    default = (1200, 800)
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return max(1, int(value[0])), max(1, int(value[1]))
    if isinstance(value, dict):
        return (max(1, int(value.get("width", default[0]))),
                max(1, int(value.get("height", default[1]))))
    text = str(value or "").lower().replace("×", "x").strip()
    parts = text.split("x")
    if len(parts) == 2:
        try:
            return max(1, int(parts[0])), max(1, int(parts[1]))
        except ValueError:
            pass
    return default


def groups() -> List[Dict[str, Any]]:
    """给组件设置面板用的分组描述（只含组件级设置）。"""
    order = [GROUP_MODEL, GROUP_RENDER, GROUP_GAZE, GROUP_IDLE,
             GROUP_MOTION, GROUP_AUDIO, GROUP_FACE, GROUP_DIALOGUE]
    return [
        {
            "name": g,
            "keys": [s["key"] for s in SETTINGS
                     if s["group"] == g and s["key"] not in PUBLIC_KEYS],
            "count": sum(1 for s in SETTINGS
                         if s["group"] == g and s["key"] not in PUBLIC_KEYS),
        }
        for g in order
    ]


# ── 配置分层 ─────────────────────────────────────────────────────
# 对外 5 项必须与 services/config.py::Live2DConfig.fields 完全一致。
# 顺序刻意与基线一致，方便存档升级和文档对照。
PUBLIC_KEYS: tuple[str, ...] = (
    "model_path",
    "canvas_size",
    "fps",
    "enable_audio_sync",
    "pipeface_model_path",
)

# 组件 UI 设置 = 全部键减去对外 5 项
COMPONENT_KEYS: tuple[str, ...] = tuple(
    s["key"] for s in SETTINGS if s["key"] not in PUBLIC_KEYS
)


def public_defaults() -> Dict[str, Any]:
    """5 个对外字段的默认值（供 Live2DConfig 与文档核对）。"""
    return {k: _clone(DEFAULTS[k]) for k in PUBLIC_KEYS}


def component_specs() -> List[Dict[str, Any]]:
    """组件设置面板要渲染的字段描述（不含对外 5 项）。"""
    return [dict(s) for s in SETTINGS if s["key"] not in PUBLIC_KEYS]


def split_public(raw: Dict[str, Any] | None) -> Dict[str, Any]:
    """从任意配置字典里只挑出 5 个对外字段（丢弃组件设置）。"""
    return {k: _coerce(k, raw[k]) for k in PUBLIC_KEYS
            if raw and k in raw}


def split_component(raw: Dict[str, Any] | None) -> Dict[str, Any]:
    """从任意配置字典里只挑出组件级设置（丢弃对外 5 项）。"""
    return {k: _coerce(k, raw[k]) for k in COMPONENT_KEYS
            if raw and k in raw}
