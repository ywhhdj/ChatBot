import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';

/// 可选相机预览（默认关闭，S7.3）。生命周期内显式释放，修 U44。
class CameraLayer extends StatefulWidget {
  const CameraLayer({super.key});

  @override
  State<CameraLayer> createState() => _CameraLayerState();
}

class _CameraLayerState extends State<CameraLayer> with WidgetsBindingObserver {
  CameraController? _camera;
  bool _ready = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _init();
  }

  Future<void> _init() async {
    if (!await Permission.camera.request().isGranted) return;
    final List<CameraDescription> cameras = await availableCameras();
    if (cameras.isEmpty || !mounted) return;
    final CameraDescription front = cameras.firstWhere(
      (CameraDescription c) => c.lensDirection == CameraLensDirection.front,
      orElse: () => cameras.first,
    );
    final CameraController controller = CameraController(
      front, ResolutionPreset.medium, enableAudio: false,
    );
    try {
      await controller.initialize();
    } catch (_) {
      await controller.dispose();
      return;
    }
    if (!mounted) {
      await controller.dispose();
      return;
    }
    _camera = controller;
    _ready = true;
    setState(() {});
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.inactive || state == AppLifecycleState.paused) {
      _release();
    } else if (state == AppLifecycleState.resumed) {
      _init();
    }
  }

  Future<void> _release() async {
    await _camera?.dispose();
    _camera = null;
    _ready = false;
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _release();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final CameraController? c = _camera;
    if (!_ready || c == null) return const SizedBox.shrink();
    return FittedBox(
      fit: BoxFit.cover,
      child: SizedBox(
        width: c.value.previewSize?.height ?? 1,
        height: c.value.previewSize?.width ?? 1,
        child: CameraPreview(c),
      ),
    );
  }
}
