class AppConfig {
  /// PC 端 WebSocket 地址。建议做成扫码/设置项动态填入。
  static String wsUrl = 'ws://192.168.1.100:8765/ws';

  /// 姿态流发送频率上限（Hz）
  static const int poseSendHz = 30;

  /// 右滑触发速度阈值（负值，绝对值越大越难触发）
  static const double swipeRightVelocity = -500;

  /// 触发冷却时间，避免连续触发动画
  static const Duration triggerCooldown = Duration(seconds: 3);

  /// Live2D 模型资源路径（相对 assets）
  static const String live2dModelPath = 'assets/live2d/Hiyori/Hiyori.model3.json';

  /// 触发“跳出”动画的 motion group 名称（需与模型定义一致）
  static const String jumpOutGroup = 'JumpOut';
}