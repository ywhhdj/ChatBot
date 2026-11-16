import 'package:camera/camera.dart';
import 'package:flutter/material.dart';

import '../../app/gal_palette.dart';
import '../../core/config/app_config.dart';
import '../../services/platform/permissions.dart';
import '../common/retry_hint.dart';

/// 相机实时背景（默认关闭，S7.3）：作为模型背后的实时画面铺满舞台。
///
/// 修复：
/// * 回前台重复 `_init()` 会抢占 / 泄漏相机 —— 已就绪直接 return，
///   `resumed` 只在 controller 为空时重建；并发换镜头用 generation 令牌；
/// * `previewSize` 为 null 时原来给 1×1 再被 FittedBox 拉成糊画面，
///   现在用 1280×720 兜底并按屏幕方向交换宽高；
/// * `SizedBox.expand` + `Positioned.fill` 保证预览真正铺满且实时刷新；
/// * 权限拒绝 / 初始化失败给当前色系 galgame 风格的「请重试」。
class CameraLayer extends StatefulWidget {
  const CameraLayer({super.key});

  @override
  State<CameraLayer> createState() => _CameraLayerState();
}

class _CameraLayerState extends State<CameraLayer> with WidgetsBindingObserver {
  CameraController? _camera;
  bool _ready = false;
  String? _error;
  int _generation = 0;
  bool _initializing = false;

  static const Size _fallbackPreview = Size(1280, 720);

  ResolutionPreset get _preset {
    switch (AppConfig.quality) {
      case StageQuality.low:
        return ResolutionPreset.low;
      case StageQuality.medium:
        return ResolutionPreset.medium;
      case StageQuality.high:
        return ResolutionPreset.high;
    }
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _init();
  }

  Future<void> _init() async {
    // 已经就绪就不要再开一路，否则会与 initState / resumed 并发抢相机。
    if (_ready && _camera != null) return;
    if (_initializing) return;
    _initializing = true;
    final int gen = ++_generation;

    // 保险：先释放可能残留的旧 controller（切镜头/档位通常靠外层 ValueKey 重建）。
    final CameraController? stale = _camera;
    _camera = null;
    _ready = false;
    if (stale != null) {
      try {
        await stale.dispose();
      } catch (_) {}
    }

    if (!await Permissions.camera()) {
      _initializing = false;
      if (gen == _generation && mounted) {
        setState(() => _error = '相机权限未授予 · 请重试或到系统设置开启');
      }
      return;
    }
    if (gen != _generation || !mounted) {
      _initializing = false;
      return;
    }

    final List<CameraDescription> cameras;
    try {
      cameras = await availableCameras();
    } catch (e) {
      _initializing = false;
      if (gen == _generation && mounted) {
        setState(() => _error = '相机不可用：$e · 请重试');
      }
      return;
    }
    if (cameras.isEmpty || gen != _generation || !mounted) {
      _initializing = false;
      return;
    }

    final CameraLensDirection lens = AppConfig.cameraFacing == CameraSide.front
        ? CameraLensDirection.front
        : CameraLensDirection.back;
    final bool hasLens =
        cameras.any((CameraDescription c) => c.lensDirection == lens);
    if (!hasLens) {
      _initializing = false;
      if (mounted) {
        setState(() => _error =
            '没有${lens == CameraLensDirection.front ? '前置' : '后置'}摄像头 · 请重试或在设定里换一面');
      }
      return;
    }
    final CameraDescription chosen = cameras.firstWhere(
      (CameraDescription c) => c.lensDirection == lens,
      orElse: () => cameras.first,
    );
    final CameraController controller = CameraController(
      chosen, _preset, enableAudio: false,
    );
    try {
      await controller.initialize();
    } catch (e) {
      try {
        await controller.dispose();
      } catch (_) {}
      _initializing = false;
      if (gen == _generation && mounted) {
        setState(() => _error = '相机初始化失败 · 请重试');
      }
      return;
    }
    if (gen != _generation || !mounted) {
      try {
        await controller.dispose();
      } catch (_) {}
      _initializing = false;
      return;
    }
    _camera = controller;
    _ready = true;
    _error = null;
    _initializing = false;
    if (mounted) setState(() {});
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused ||
        state == AppLifecycleState.hidden) {
      _release();
    } else if (state == AppLifecycleState.resumed &&
        AppConfig.cameraEnabled &&
        _camera == null) {
      // 只在确实释放过（_camera == null）时重建，避免与首次 init 抢相机。
      _init();
    }
  }

  Future<void> _release() async {
    _generation++;
    _initializing = false;
    final CameraController? c = _camera;
    _camera = null;
    _ready = false;
    if (c != null) {
      try {
        await c.dispose();
      } catch (_) {}
    }
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _generation++;
    _initializing = false;
    final CameraController? c = _camera;
    _camera = null;
    _ready = false;
    try {
      c?.dispose();
    } catch (_) {}
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final CameraController? c = _camera;
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 32),
          child: RetryHint(
            compact: true,
            title: '相机未开启',
            detail: _error!,
            onRetry: _init,
          ),
        ),
      );
    }
    if (!_ready || c == null) {
      return Center(
        child: Text('…… 正在开启相机背景 ……',
            style: TextStyle(
                color: GalPalette.of(context).textFaint, fontSize: 11)),
      );
    }

    // previewSize 是相机的横向像素尺寸；竖屏要交换宽高，且必须有可用的兜底值，
    // 否则 1×1 被 FittedBox 放大后就是一片糊，看起来「不是实时画面」。
    final Size preview = c.value.previewSize ?? _fallbackPreview;
    final bool portrait =
        MediaQuery.of(context).orientation == Orientation.portrait;
    final double w = portrait ? preview.height : preview.width;
    final double h = portrait ? preview.width : preview.height;

    return SizedBox.expand(
      child: FittedBox(
        fit: BoxFit.cover,
        clipBehavior: Clip.hardEdge,
        child: SizedBox(
          width: w,
          height: h,
          child: CameraPreview(c),
        ),
      ),
    );
  }
}
