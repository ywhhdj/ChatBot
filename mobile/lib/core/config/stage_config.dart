/// 舞台动画参数（纯数据）。组件层读取，状态机只输出数值。
class StageConfig {
  static const double flingRotationDeg = 12.0;
  static const double flingScale = 0.92;
  static const double flingOvershootFactor = 1.2;
  static const double peekVisibleFraction = 0.34;
  static const double peekOvershoot = 8.0;
  static const double turnLimitDeg = 30.0;
  static const double tiltPerDeg = 0.18;
  static const double screenWidthFactor = 1.2;
  static const double dialogOpacity = 0.82;
  static const int hudRefreshHz = 4;
  static const int debugRingMaxItems = 200;
  static const int debugRingMaxBytes = 512 * 1024;
}
