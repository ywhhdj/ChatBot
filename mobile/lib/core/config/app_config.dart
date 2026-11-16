import '../../app/gal_palette.dart';
import 'model_config.dart';

/// 性能档位：相机分辨率、姿态频率、目标帧率建议值。
enum StageQuality { low, medium, high }

/// 语音识别来源：无电脑端 / 离线时自动回退到系统内置识别。
enum AsrMode { auto, server, system }

/// 相机实时背景用前置还是后置（扫码页始终用后置，不受影响）。
enum CameraSide { front, back }

/// 全局配置：一次读入内存，禁止每帧查 SharedPreferences。
class AppConfig {
  AppConfig._();

  // ---- 连接 ----
  static const int defaultPort = 8000;
  static const String defaultWsPath = '/';
  static String wsUrl = '';
  /// 「跳过扫码」进入离线单机时记住的上次地址，供设定页一键重连。
  static String suggestedWsUrl = '';
  static String uid = '';
  static String token = '';
  static const String device = 'mobile';

  // ---- 外观 ----
  static GalScheme scheme = GalScheme.blue;
  /// 只关界面切换类动画；Live2D 演出与舞台帧泵始终保留。
  /// 注意：**不**自动关逐字机，逐字机由 `disableTypewriter` 单独控制。
  static bool reduceAnimations = false;
  /// 逐字机默认保留（galgame 台词演出的一部分），只有用户明确打开才全显。
  static bool disableTypewriter = false;
  static CameraSide cameraFacing = CameraSide.front;

  // ---- 输入 / 历史去重 ----
  /// 短时间内连续提交的文本合并成一条再发送（0 = 关闭）。
  static int inputDebounceMs = 220;
  static bool inputMergeEnabled = true;
  /// 相邻重复（与上一条相同或连续 ASR 中间结果）直接丢弃。
  static bool dedupeAdjacent = true;

  // ---- 姿态流 ----
  static int poseSendHz = 18;
  static double poseLowPassK = 0.22;
  static double poseDeadZoneDeg = 2.0;
  static int poseCalibrationFrames = 10;

  // ---- 手势 ----
  static double swipeRightVelocity = 800.0;
  static double swipeMinDistance = 60.0;
  static double swipeMaxDurationMs = 600.0;
  static double swipeDominance = 1.2;
  static int triggerCooldownMs = 3000;
  static double turnStepDeg = 18.0;
  static Duration get triggerCooldown => Duration(milliseconds: triggerCooldownMs);

  // ---- 演出时序 ----
  static int flingDurationMs = 420;
  static int peekDelayMs = 1600;
  static int peekHoldMs = 900;
  static int returnDurationMs = 480;
  static Duration get flingDuration => Duration(milliseconds: flingDurationMs);
  static Duration get peekDelay => Duration(milliseconds: peekDelayMs);
  static Duration get peekHoldDuration => Duration(milliseconds: peekHoldMs);
  static Duration get returnDuration => Duration(milliseconds: returnDurationMs);

  // ---- 帧率 / 省电 / 置顶 ----
  static int targetFps = 60;
  static int overlayFps = 15;
  static bool showFps = false;
  static bool powerSaveEnabled = true;
  static bool overlayEnabled = false;
  static bool overlayActive = false;
  /// 置顶时缩小在右侧并默认「右侧探头」，避免遮挡又不至于看不见模型。
  static bool overlayPeekEnabled = true;
  static double overlayScale = 0.55;

  // ---- 语音识别 ----
  static AsrMode asrMode = AsrMode.auto;

  // ---- 模型 ----
  static String modelDir = '';
  static String modelDirUri = '';
  static bool modelPreviewEnabled = true;

  // ---- 网络 ----
  static const Duration heartbeatInterval = Duration(seconds: 30);
  static const Duration reconnectBase = Duration(seconds: 1);
  static const Duration reconnectMax = Duration(seconds: 10);
  static const int maxPendingFrames = 64;
  static const int maxStageSeqHistory = 256;
  static int maxReconnectAttempts = 8;
  static bool autoReconnect = true;
  static bool mirrorTextInput = false;
  static bool mirrorAsrText = true;

  // ---- 内容 ----
  static const String jumpOutGroup = 'JumpOut';
  static const int maxTextLength = 2000;
  static const int maxHistoryItems = 100;
  static int typewriterCps = 32;

  // ---- 可持久化项 ----
  static StageQuality quality = StageQuality.medium;
  static bool cameraEnabled = false;
  static bool autoSendAsr = true;
  static String characterName = '她';
  static String activeModelId = ModelConfig.fallback.id;

  static ModelConfig get activeModel => ModelConfig.byId(activeModelId);
  static int get animationTargetFps => targetFps.clamp(1, 144).toInt();

  static int get suggestedFps {
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
  static bool get keepAliveInBackground =>
      powerSaveEnabled && overlayEnabled && overlayActive;

  /// 设定页「恢复默认」：只重置可调参数，不动 uid / 连接地址 / 模型目录 / 色系。
  static void restoreDefaults() {
    poseSendHz = 18;
    poseLowPassK = 0.22;
    poseDeadZoneDeg = 2.0;
    poseCalibrationFrames = 10;
    swipeRightVelocity = 800.0;
    swipeMinDistance = 60.0;
    swipeMaxDurationMs = 600.0;
    swipeDominance = 1.2;
    triggerCooldownMs = 3000;
    turnStepDeg = 18.0;
    flingDurationMs = 420;
    peekDelayMs = 1600;
    peekHoldMs = 900;
    returnDurationMs = 480;
    targetFps = 60;
    showFps = false;
    powerSaveEnabled = true;
    reduceAnimations = false;
    disableTypewriter = false; // 默认保留逐字机，只有明确指定才关
    cameraFacing = CameraSide.front;
    inputDebounceMs = 220;
    inputMergeEnabled = true;
    dedupeAdjacent = true;
    overlayPeekEnabled = true;
    overlayScale = 0.55;
    asrMode = AsrMode.auto;
    modelPreviewEnabled = true;
    maxReconnectAttempts = 8;
    autoReconnect = true;
    mirrorTextInput = false;
    mirrorAsrText = true;
    typewriterCps = 32;
    quality = StageQuality.medium;
    cameraEnabled = false;
    autoSendAsr = true;
  }
}
