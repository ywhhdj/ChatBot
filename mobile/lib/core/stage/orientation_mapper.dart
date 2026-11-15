import 'stage_transform.dart';
import '../config/app_config.dart';
import '../config/stage_config.dart';

/// gamma -> 身体左右 / beta -> 俯仰 / alpha -> 整体偏转；限幅 + 低通 + 死区（S3.4）。
class OrientationMapper {
  double _turn = 0.0;
  double _tilt = 0.0;

  StageTransform map(double alpha, double beta, double gamma) {
    final double targetTurn = _clamp(gamma, -StageConfig.turnLimitDeg,
        StageConfig.turnLimitDeg);
    final double targetTilt = _clamp(beta * StageConfig.tiltPerDeg, -12.0, 12.0);
    _turn += AppConfig.poseLowPassK * (targetTurn - _turn);
    _tilt += AppConfig.poseLowPassK * (targetTilt - _tilt);
    if (targetTurn.abs() < AppConfig.poseDeadZoneDeg &&
        targetTilt.abs() < AppConfig.poseDeadZoneDeg) {
      return StageTransform(turnDeg: _turn);
    }
    return StageTransform(
      turnDeg: _turn,
      rotationRad: _tilt * 3.141592653589793 / 180.0,
    );
  }

  void reset() {
    _turn = 0;
    _tilt = 0;
  }

  static double _clamp(double v, double lo, double hi) =>
      v < lo ? lo : (v > hi ? hi : v);
}
