/// 舞台变换数值：core 只输出 double，组件层负责 Transform / ClipRect
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

  /// 完全不可见（出屏 / 缩到 0）：组件层据此整棵跳过绘制，
  /// 避免模型被 Transform 到屏幕外仍然提交 GPU（离屏绘制）。
  bool get culled => opacity <= 0.001 || scale <= 0.001;

  /// 置顶浮窗：缩小并停在右侧「探头」位置，避免遮挡其它应用又不至于看不见模型。
  /// 纯数据，StageView 与单元测试共用。
  static StageTransform overlayPeek({
    required double width,
    required double scale,
    required double peekFraction,
    required double overshoot,
    double turnDeg = 0,
  }) =>
      StageTransform(
        dx: width * (1 - peekFraction) - overshoot,
        scale: scale,
        opacity: 1,
        peekClip: true,
        peekFraction: peekFraction,
        turnDeg: turnDeg,
      );

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
