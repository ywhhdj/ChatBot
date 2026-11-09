import 'dart:async';
import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter_live2d/flutter_live2d.dart';
import 'package:permission_handler/permission_handler.dart';

import '../config.dart';
import '../api/pose.dart';
import '../api/ws.dart';

class ArLive2DPage extends StatefulWidget {
  const ArLive2DPage({super.key});

  @override
  State<ArLive2DPage> createState() => _ArLive2DPageState();
}

class _ArLive2DPageState extends State<ArLive2DPage>
    with WidgetsBindingObserver {
  CameraController? _camera;
  Live2dController? _live2d;

  late PoseService _poseService;
  late WsService _wsService;

  DateTime _lastTrigger = DateTime.fromMillisecondsSinceEpoch(0);
  bool _cameraReady = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);

    _wsService = WsService(
      url: AppConfig.wsUrl,
      onRemoteEvent: (event) {
        // PC 端可能反过来通知手机播动画（可选）
        if (event == 'jump_out') _playJumpOutLocal();
      },
    )..connect();

    _poseService = PoseService(
      sendHz: AppConfig.poseSendHz,
      onPose: (a, b, g, t) => _wsService.sendPose(a, b, g, t),
    );
    _poseService.start();

    _initCamera();
    _initLive2D();
  }

  Future<void> _initCamera() async {
    final status = await Permission.camera.request();
    if (!status.isGranted) return;

    final cameras = await availableCameras();
    if (cameras.isEmpty) return;

    final front = cameras.firstWhere(
      (c) => c.lensDirection == CameraLensDirection.front,
      orElse: () => cameras.first,
    );

    final controller = CameraController(
      front,
      ResolutionPreset.high,
      enableAudio: false,
      imageFormatGroup: ImageFormatGroup.yuv420,
    );
    await controller.initialize();
    if (!mounted) {
      controller.dispose();
      return;
    }
    setState(() {
      _camera = controller;
      _cameraReady = true;
    });
  }

  void _initLive2D() {
    _live2d = Live2dController();
    _live2d!.setModel(AppConfig.live2dModelPath).then((_) {
      // 可选：初始化完成后播放默认待机动画
    });
  }

  void _playJumpOutLocal() {
    _live2d?.startMotion(AppConfig.jumpOutGroup);
  }

  /// 手势：手指向右快速滑动 → 触发跳出
  void _onHorizontalDragEnd(DragEndDetails details) {
    final v = details.primaryVelocity ?? 0;
    if (v > AppConfig.swipeRightVelocity) return; // 不是右滑
    final now = DateTime.now();
    if (now.difference(_lastTrigger) < AppConfig.triggerCooldown) return;
    _lastTrigger = now;

    _playJumpOutLocal();
    _wsService.sendTrigger('jump_out', timestampMs: now.millisecondsSinceEpoch);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.inactive) {
      _camera?.dispose();
    } else if (state == AppLifecycleState.resumed && _cameraReady) {
      _initCamera();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _camera?.dispose();
    _poseService.dispose();
    _wsService.dispose();
    _live2d?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onHorizontalDragEnd: _onHorizontalDragEnd,
        child: Stack(
          fit: StackFit.expand,
          children: [
            // 1. 相机预览层
            if (_cameraReady && _camera != null)
              _buildCameraPreview()
            else
              const Center(child: CircularProgressIndicator()),

            // 2. Live2D 叠加层（透明背景，全屏居中）
            IgnorePointer(
              // 让手势完全交给外层 GestureDetector
              child: Center(
                child: _live2d == null
                    ? const SizedBox.shrink()
                    : Live2dView(controller: _live2d!),
              ),
            ),

            // 3. 简单状态指示
            Positioned(
              top: 40,
              left: 16,
              child: _StatusChip(
                connected: _wsService.isConnected,
                hint: '右滑触发跳出',
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCameraPreview() {
    final controller = _camera!;
    final size = controller.value.previewSize!;
    // 竖屏预览，交换宽高并裁剪填满
    return FittedBox(
      fit: BoxFit.cover,
      child: SizedBox(
        width: size.height,
        height: size.width,
        child: CameraPreview(controller),
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  final bool connected;
  final String hint;
  const _StatusChip({required this.connected, required this.hint});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.black54,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.circle,
              size: 10,
              color: connected ? Colors.greenAccent : Colors.redAccent),
          const SizedBox(width: 6),
          Text(hint,
              style: const TextStyle(color: Colors.white, fontSize: 12)),
        ],
      ),
    );
  }
}