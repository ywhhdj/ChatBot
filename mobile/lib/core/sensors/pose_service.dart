import 'dart:async';
import 'dart:math' as math;
import 'package:flutter_rotation_sensor/flutter_rotation_sensor.dart';

import '../config/app_config.dart';

/// 姿态采集：一阶低通 + 死区 + 零位校准 + 节流，静止时接近 0 帧（S2.3 / U16 兜底）。
/// sendHz 可在设定页调整，无需重建订阅（避免重连传感器造成内存抖动）。
class PoseService {
  PoseService({required this.onPose, int? sendHz})
      : _intervalMs = _hzToIntervalMs(sendHz ?? AppConfig.poseSendHz);

  final void Function(double alpha, double beta, double gamma, int t) onPose;
  int _intervalMs;

  StreamSubscription<OrientationEvent>? _sub;
  int _lastSentMs = 0;
  bool _paused = false;
  bool _disposed = false;
  double _fa = 0, _fb = 0, _fg = 0;
  double _ca = 0, _cb = 0, _cg = 0;
  int _calibCount = 0;
  bool _calibrated = false;

  static int _hzToIntervalMs(int hz) {
    final int safe = hz.clamp(1, 60).toInt();
    return (1000 / safe).round();
  }

  void setHz(int hz) => _intervalMs = _hzToIntervalMs(hz);

  Future<void> start() async {
    if (_disposed || _sub != null) return;
    RotationSensor.samplingPeriod = SensorInterval.uiInterval;
    _sub = RotationSensor.orientationStream.listen(_onOrientation);
  }

  void _onOrientation(OrientationEvent orientation) {
    if (_paused || _disposed) return;
    final int now = DateTime.now().millisecondsSinceEpoch;
    if (now - _lastSentMs < _intervalMs) return;

    final double rad2deg = 180.0 / math.pi;
    final double a = orientation.eulerAngles.azimuth * rad2deg;
    final double b = orientation.eulerAngles.pitch * rad2deg;
    final double g = orientation.eulerAngles.roll * rad2deg;

    if (!_calibrated) {
      _ca += a; _cb += b; _cg += g;
      _calibCount++;
      if (_calibCount < AppConfig.poseCalibrationFrames) return;
      _ca /= _calibCount; _cb /= _calibCount; _cg /= _calibCount;
      _calibrated = true;
    }

    final double a0 = a - _ca, b0 = b - _cb, g0 = g - _cg;
    final double k = AppConfig.poseLowPassK;
    _fa += k * (a0 - _fa);
    _fb += k * (b0 - _fb);
    _fg += k * (g0 - _fg);

    final double delta = (_fa - a0).abs() + (_fb - b0).abs() + (_fg - g0).abs();
    if (delta < AppConfig.poseDeadZoneDeg &&
        (_fa - a0).abs() < AppConfig.poseDeadZoneDeg &&
        (_fg - g0).abs() < AppConfig.poseDeadZoneDeg) {
      return;
    }
    _lastSentMs = now;
    onPose(_fa, _fb, _fg, now);
  }

  void pause() => _paused = true;
  void resume() => _paused = false;

  Future<void> dispose() async {
    _disposed = true;
    _paused = true;
    final StreamSubscription<OrientationEvent>? sub = _sub;
    _sub = null;
    if (sub != null) await sub.cancel();
  }
}
