"""Live2D / Galgame 的**纯逻辑**离线测试（不需要 Qt、OpenGL、GPU、模型文件）。

跑法
────
```bash
python src/tests/test_live2d.py
python -m unittest src.tests.test_live2d -v
pytest src/tests/test_live2d.py -q
```

用例本体在 ``modules/services/live2d/selftest.py``，与
``src/tests/test_live2d_ui.py``（创建视图测试）共用同一套逻辑。
本文件额外覆盖**配置分层**：对外配置保持基线 5 项不变，其余 107 项
显示设置只属于组件 UI、只写 ``ui_settings.json``、不进存档 / 不注册 API；
老存档带旧版 112 项时不能报错、不能把组件键写回 ``to_dict()``。

UI 组件树是否正常由 ``test_live2d_ui.py`` 直接创建视图验证，**不走 HTTP**。
"""
from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]       # <repo>/src
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _ensure_importable() -> None:
    """沙盒/精简环境里补两个可选依赖的桩，避免 import 链半路炸掉。"""
    def noop(*_a, **_k):
        return None

    if "modules.utils.http" not in sys.modules:
        m = types.ModuleType("modules.utils.http")
        m.__path__ = []  # type: ignore[attr-defined]
        for name in (
            "download_file", "async_get", "async_post",
            "create_httpx_async_client", "remote_stream", "get", "post",
            "http_exceptions", "create_httpx_sync_client",
        ):
            setattr(m, name, noop)
        sys.modules["modules.utils.http"] = m
    for name in ("modules.core.pipeline.emotion",
                 "modules.core.pipeline.emotion.predictor"):
        if name not in sys.modules:
            m = types.ModuleType(name)
            m.__path__ = []  # type: ignore[attr-defined]
            sys.modules[name] = m
    sys.modules["modules.core.pipeline.emotion.predictor"].id_to_name = (  # type: ignore[attr-defined]
        lambda _i: "neutral")

    import modules.runtime as rt
    if getattr(rt, "manager", None) is None:
        class _Bus:
            def on(self, *_a, **_k): pass
            def off(self, *_a, **_k): pass
            def emit(self, *_a, **_k): return None
        rt.manager = types.SimpleNamespace(event_bus=_Bus())


_ensure_importable()

from modules.services.live2d.component_settings import (  # noqa: E402
    ComponentSettingsStore,
)
from modules.services.live2d.selftest import (  # noqa: E402
    CASE_NAMES, gaze_trace, run_suite,
)
from modules.services.live2d.settings import (  # noqa: E402
    COMPONENT_KEYS, DEFAULTS, PUBLIC_KEYS, component_specs, groups, normalize,
    public_defaults, split_component, split_public,
)


class TestOfflineSuite(unittest.TestCase):
    """把 selftest 的每个用例映射成一个 subTest。"""

    def test_all_cases(self):
        result = run_suite()
        for case in result["cases"]:
            with self.subTest(case=case["name"]):
                self.assertTrue(case["ok"], f"{case['name']} -> {case['detail']}")
        self.assertEqual(result["failed"], 0,
                         f"{result['failed']}/{result['total']} 个用例失败")
        self.assertEqual(result["total"], 18)
        self.assertTrue(result["ok"])

    def test_suite_coverage(self):
        names = " ".join(CASE_NAMES).lower()
        for keyword in ("gaze", "idle", "lipsync", "emotion", "perf",
                        "dialogue", "settings", "engine"):
            self.assertIn(keyword, names, f"缺少 {keyword} 相关用例")
        self.assertGreaterEqual(len(CASE_NAMES), 15)


class TestConfigLayering(unittest.TestCase):
    """对外 5 项 / 组件 UI 107 项，两层互不污染。"""

    def test_public_config_is_exactly_baseline_five(self):
        from modules.services.config import Live2DConfig

        self.assertEqual(len(PUBLIC_KEYS), 5)
        self.assertEqual(set(public_defaults()), set(PUBLIC_KEYS))
        cfg = Live2DConfig()
        fields = {f["key"] for f in cfg.get_ui_config_items()["fields"]}
        self.assertEqual(fields, set(PUBLIC_KEYS))
        dumped = cfg.to_dict()
        self.assertEqual(set(dumped) - {"service", "name", "enabled"},
                         set(PUBLIC_KEYS))
        for k in ("gaze_when_no_face", "is_face_detected",
                  "dialogue_typing_cps", "idle_expression_weights"):
            self.assertNotIn(k, dumped, "组件设置泄漏进对外配置")

    def test_component_keys_are_all_other_settings(self):
        self.assertEqual(len(COMPONENT_KEYS), 107)
        self.assertEqual(len(DEFAULTS), 112)
        self.assertFalse(set(PUBLIC_KEYS) & set(COMPONENT_KEYS))
        self.assertEqual(set(PUBLIC_KEYS) | set(COMPONENT_KEYS), set(DEFAULTS))
        self.assertEqual(len(component_specs()), 107)
        gs = groups()
        self.assertEqual(len(gs), 8)
        self.assertEqual(sum(g["count"] for g in gs), 107)

    def test_split_helpers(self):
        mixed = {**{k: DEFAULTS[k] for k in PUBLIC_KEYS},
                 "gaze_when_no_face": False, "dialogue_typing_cps": 42}
        self.assertEqual(set(split_public(mixed)), set(PUBLIC_KEYS))
        self.assertNotIn("gaze_when_no_face", split_public(mixed))
        comp = split_component(mixed)
        self.assertEqual(comp["dialogue_typing_cps"], 42)
        self.assertFalse(comp["gaze_when_no_face"])
        self.assertNotIn("model_path", comp)

    def test_old_save_with_112_keys_does_not_leak(self):
        """旧存档把 112 项都塞进 Live2DConfig：不报错，但 to_dict 仍只有 5 项。"""
        from modules.services.config import Live2DConfig

        legacy = {"model_path": "a.model3.json", "canvas_size": "800x600",
                  "fps": 30, "enable_audio_sync": True,
                  "pipeface_model_path": "m.task",
                  "is_face_detected": True, "gaze_when_no_face": False,
                  "dialogue_typing_cps": 42}
        cfg = Live2DConfig(**legacy)
        self.assertEqual(cfg.fps, 30)
        self.assertTrue(cfg.is_face_detected)      # 兼容：多余键挂在实例上
        dumped = cfg.to_dict()
        self.assertEqual(set(dumped) - {"service", "name", "enabled"},
                         set(PUBLIC_KEYS))
        self.assertNotIn("gaze_when_no_face", dumped)
        self.assertNotIn("dialogue_typing_cps", dumped)
        restored = Live2DConfig(**json.loads(json.dumps(dumped)))
        self.assertEqual(restored.fps, 30)

    def test_numeric_clamping_and_legacy_aliases(self):
        cfg = normalize({"fps": 0, "opacity": 99, "render_scale": 5,
                         "dialogue_typing_cps": -10, "idle_fps": 9999,
                         "media_pipe_face_model_path": "X.task",
                         "window_size": [800, 600]})
        self.assertGreaterEqual(cfg["fps"], 1)
        self.assertLessEqual(cfg["opacity"], 1)
        self.assertLessEqual(cfg["render_scale"], 1.0)
        self.assertGreaterEqual(cfg["dialogue_typing_cps"], 1)
        self.assertLessEqual(cfg["idle_fps"], 144)
        self.assertEqual(cfg["pipeface_model_path"], "X.task")
        self.assertEqual(cfg["canvas_size"], "800x600")


class TestComponentSettingsStore(unittest.TestCase):
    """组件设置只写 ui_settings.json；对外 5 项由 merge 时覆盖。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="chatbot-l2d-cfg-")
        self.addCleanup(self._tmp.cleanup)
        self.store = ComponentSettingsStore(
            Path(self._tmp.name) / "live2d" / "ui_settings.json")

    def test_load_defaults_and_save_filter(self):
        data = self.store.load()
        self.assertEqual(set(data), set(COMPONENT_KEYS))
        self.assertFalse(set(data) & set(PUBLIC_KEYS))
        self.assertFalse(self.store.exists)

        saved = self.store.save({**data, "fps": 999,
                                 "model_path": "should-not-persist",
                                 "gaze_smoothing": 0.7})
        self.assertEqual(set(saved), set(COMPONENT_KEYS))
        self.assertEqual(saved["gaze_smoothing"], 0.7)
        raw = json.loads(self.store.path.read_text("utf-8"))
        self.assertEqual(set(raw), set(COMPONENT_KEYS))
        self.assertNotIn("fps", raw)
        self.assertNotIn("model_path", raw)
        self.assertTrue(self.store.exists)

    def test_patch_and_reset(self):
        self.store.patch({"gaze_sensitivity": 2.5})
        self.assertEqual(self.store.load()["gaze_sensitivity"], 2.5)
        self.store.patch({"dialogue_typing_cps": 45})
        self.assertEqual(self.store.load()["dialogue_typing_cps"], 45)
        self.assertEqual(self.store.load()["gaze_sensitivity"], 2.5)
        self.store.reset()
        self.assertNotEqual(self.store.load()["gaze_sensitivity"], 2.5)

    def test_merge_public_overrides_component(self):
        full = self.store.merge({"fps": 45, "canvas_size": "900x600"})
        self.assertEqual(set(full), set(DEFAULTS))
        self.assertEqual(full["fps"], 45)
        self.assertEqual(full["canvas_size"], "900x600")
        # 组件设置打底，不被对外默认值冲掉
        self.store.patch({"gaze_smoothing": 0.3})
        full2 = self.store.merge({"fps": 45})
        self.assertEqual(full2["gaze_smoothing"], 0.3)
        self.assertEqual(full2["fps"], 45)
        self.assertEqual(set(self.store.public_view(full2)), set(PUBLIC_KEYS))
        self.assertEqual(set(self.store.component_view(full2)),
                         set(COMPONENT_KEYS))

    def test_corrupt_file_falls_back_to_defaults(self):
        self.store.path.parent.mkdir(parents=True, exist_ok=True)
        self.store.path.write_text("{not json", "utf-8")
        self.store.clear_cache()
        self.assertEqual(set(self.store.load()), set(COMPONENT_KEYS))


class TestGazeTrace(unittest.TestCase):
    def test_trace_shape(self):
        trace = gaze_trace()
        self.assertEqual(trace["points"], 8)
        self.assertEqual(len(trace["frames"]), 8)
        self.assertEqual(trace["params"], ["ParamAngleX", "ParamEyeBallX"])
        for frame in trace["frames"]:
            self.assertIn("angle_x", frame)
            self.assertIn("eyeball_x", frame)
            self.assertLessEqual(abs(frame["angle_x"]), 1.0)

    def test_custom_points(self):
        trace = gaze_trace(points=[[1.0, 0.0], [-1.0, 0.0]])
        self.assertEqual(trace["points"], 2)
        self.assertGreater(trace["frames"][0]["angle_x"], 0)


if __name__ == "__main__":
    print("=" * 72)
    print("Live2D / Galgame 纯逻辑测试（无需 Qt / OpenGL / GPU / HTTP）")
    print("=" * 72)
    result = run_suite()
    for c in result["cases"]:
        mark = "PASS" if c["ok"] else "FAIL"
        detail = c["detail"] if isinstance(c["detail"], str) else json.dumps(
            c["detail"], ensure_ascii=False)[:110]
        print(f"  [{mark}] {c['name']}  ({c['ms']}ms) {detail}")
    print(f"\n{result['passed']}/{result['total']} 通过，耗时 {result['elapsed_ms']}ms")
    print("\nunittest 详细模式：")
    unittest.main(verbosity=2, exit=False)
    if not result["ok"]:
        sys.exit(1)
