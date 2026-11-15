import 'model_config.dart';

/// 性能档位：相机分辨率、姿态频率、目标帧率。
enum StageQuality { low, medium, high }

/// 全局配置：一次读入内存，禁止每帧查 SharedPreferences。
class AppConfig {
  AppConfig._();

  // ---- 连接 ----
  static const int defaultPort = 8000;
  static const String defaultWsPath = '/';
  static String wsUrl = '';

  // ---- 姿态流 ----
  static const int poseSendHz = 18;
  static const double poseLowPassK = 0.22;
  static const double poseDeadZoneDeg = 2.0;
  static const int poseCalibrationFrames = 10;

  // ---- 手势 ----
  static const double swipeRightVelocity = 800.0;
  static const double swipeMinDistance = 60.0;
  static const double swipeMaxDurationMs = 600.0;
  static const double swipeDominance = 1.2;
  static const Duration triggerCooldown = Duration(seconds: 3);

  // ---- 演出时序 ----
  static const Duration flingDuration = Duration(milliseconds: 420);
  static const Duration peekDelay = Duration(milliseconds: 1600);
  static const Duration peekHoldDuration = Duration(milliseconds: 900);
  static const Duration returnDuration = Duration(milliseconds: 480);

  // ---- 网络 ----
  static const Duration heartbeatInterval = Duration(seconds: 30);
  static const Duration reconnectBase = Duration(seconds: 1);
  static const Duration reconnectMax = Duration(seconds: 10);
  static const int maxPendingFrames = 64;
  static const int maxStageSeqHistory = 256;

  // ---- 内容 ----
  static const String jumpOutGroup = 'JumpOut';
  static const int maxTextLength = 2000;
  static const int maxHistoryItems = 100;
  static const int typewriterCps = 32;

  // ---- 可持久化项 ----
  static StageQuality quality = StageQuality.medium;
  static bool cameraEnabled = false;
  static bool autoSendAsr = true;
  static String characterName = '她';
  static String activeModelId = ModelConfig.fallback.id;

  static ModelConfig get activeModel => ModelConfig.byId(activeModelId);

  static int get animationTargetFps {
    switch (quality) {
      case StageQuality.low:
        return 30;
      case StageQuality.medium:
        return 45;
      case StageQuality.high:
        return 60;
    }
  }

  static bool get paramOrientationEnabled => quality == StageQuality.high;
}
