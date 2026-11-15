/// 舞台变换数值：core 只输出 double，组件层负责 Transform / ClipRect（§2.5.2）。
class StageTransform {
  const StageTransform({
    this.dx = 0.0,
    this.rotationRad = 0.0,
    this.scale = 1.0,
    this.opacity = 1.0,
    this.peekClip = false,
    this.peekFraction = 1.0,
    this.turnDeg = 0.0,
  });

  final double dx;
  final double rotationRad;
  final double scale;
  final double opacity;
  final bool peekClip;
  final double peekFraction;
  final double turnDeg;

  static const StageTransform idle = StageTransform();

  static double lerpDouble(double a, double b, double t) => a + (b - a) * t;

  StageTransform lerp(StageTransform other, double t) => StageTransform(
        dx: lerpDouble(dx, other.dx, t),
        rotationRad: lerpDouble(rotationRad, other.rotationRad, t),
        scale: lerpDouble(scale, other.scale, t),
        opacity: lerpDouble(opacity, other.opacity, t),
        peekClip: t < 0.5 ? peekClip : other.peekClip,
        peekFraction: lerpDouble(peekFraction, other.peekFraction, t),
        turnDeg: lerpDouble(turnDeg, other.turnDeg, t),
      );
}

/// 纯 Dart 缓动，避免 core 依赖 Flutter Curves。
class StageCurves {
  StageCurves._();

  static double easeOutQuart(double t) => 1 - _pow4(1 - t);
  static double easeInOutCubic(double t) =>
      t < 0.5 ? 4 * t * t * t : 1 - _pow3(-2 * t + 2) / 2;
  static double easeOutBack(double t) {
    const double c1 = 1.70158;
    const double c3 = c1 + 1;
    return 1 + c3 * _pow3(t - 1) + c1 * _pow2(t - 1);
  }

  static double _pow2(double x) => x * x;
  static double _pow3(double x) => x * x * x;
  static double _pow4(double x) => _pow2(x) * _pow2(x);
}
