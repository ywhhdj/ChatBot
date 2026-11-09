import 'dart:async';
import 'dart:math' as math;
import 'package:flutter_rotation_sensor/flutter_rotation_sensor.dart';

/// 采集设备姿态，输出欧拉角（度），并按频率节流回调。
class PoseService {
  final void Function(double alpha, double beta, double gamma, int timestampMs) onPose;
  final int sendHz;

  StreamSubscription<Orientation>? _sub;
  int _lastSentMs = 0;
  final int _intervalMs;

  PoseService({required this.onPose, this.sendHz = 30})
      : _intervalMs = (1000 / sendHz).round();

  Future<void> start() async {
    // 请求传感器刷新频率
    await FlutterRotationSensor.setSamplingPeriod(
      SamplingPeriod.ui,
    );

    _sub = FlutterRotationSensor.orientationStream.listen((orientation) {
      final now = DateTime.now().millisecondsSinceEpoch;
      if (now - _lastSentMs < _intervalMs) return;
      _lastSentMs = now;

      final euler = orientation.eulerAngles;
      final rad2deg = 180.0 / math.pi;
      onPose(
        euler.azimuth * rad2deg,
        euler.pitch * rad2deg,
        euler.roll * rad2deg,
        now,
      );
    });
  }

  Future<void> dispose() async {
    await _sub?.cancel();
    _sub = null;
  }
}