import 'dart:async';

import 'package:shared_preferences/shared_preferences.dart';

import '../../app/gal_palette.dart';
import '../../core/config/app_config.dart';
import '../../core/net/device_identity.dart';

/// 本地持久化：只在设置变更/启动时读写，禁止每帧访问（S7.5）。
class Prefs {
  Prefs._();

  static const String _kLastWsUrl = 'last_ws_url';
  static const String _kModelId = 'active_model_id';
  static const String _kModelDir = 'model_dir';
  static const String _kModelDirUri = 'model_dir_uri';
  static const String _kModelPreview = 'model_preview_enabled';
  static const String _kQuality = 'quality';
  static const String _kCamera = 'camera_enabled';
  static const String _kCameraFacing = 'camera_facing';
  static const String _kAutoAsr = 'auto_send_asr';
  static const String _kName = 'character_name';
  static const String _kUid = 'device_uid';
  static const String _kToken = 'auth_token';
  static const String _kSwipe = 'swipe_velocity';
  static const String _kSwipeMin = 'swipe_min_distance';
  static const String _kPoseHz = 'pose_hz';
  static const String _kDeadZone = 'pose_dead_zone';
  static const String _kLowPassK = 'pose_low_pass_k';
  static const String _kPeekMs = 'peek_delay_ms';
  static const String _kPeekHoldMs = 'peek_hold_ms';
  static const String _kFlingMs = 'fling_duration_ms';
  static const String _kReturnMs = 'return_duration_ms';
  static const String _kTypewriterCps = 'typewriter_cps';
  static const String _kTurnStep = 'turn_step_deg';
  static const String _kCooldownMs = 'trigger_cooldown_ms';
  static const String _kMirrorText = 'mirror_text_input';
  static const String _kMirrorAsr = 'mirror_asr_text';
  static const String _kAutoReconnect = 'auto_reconnect';
  static const String _kMaxAttempts = 'max_reconnect_attempts';
  static const String _kTargetFps = 'target_fps';
  static const String _kShowFps = 'show_fps';
  static const String _kPowerSave = 'power_save_enabled';
  static const String _kOverlay = 'overlay_enabled';
  static const String _kAsrMode = 'asr_mode';
  static const String _kScheme = 'gal_scheme';
  static const String _kReduceAnimations = 'reduce_animations';
  static const String _kDisableTypewriter = 'disable_typewriter';
  static const String _kInputDebounce = 'input_debounce_ms';
  static const String _kInputMerge = 'input_merge_enabled';
  static const String _kDedupe = 'dedupe_adjacent';
  static const String _kOverlayPeek = 'overlay_peek_enabled';
  static const String _kOverlayScale = 'overlay_scale';

  static Future<String?> getLastWsUrl() async =>
      (await SharedPreferences.getInstance()).getString(_kLastWsUrl);

  static Future<void> setLastWsUrl(String url) async =>
      (await SharedPreferences.getInstance()).setString(_kLastWsUrl, url);

  static T _enum<T>(List<T> values, int? index, T fallback) =>
      (index != null && index >= 0 && index < values.length)
          ? values[index]
          : fallback;

  static Future<void> loadAll() async {
    final SharedPreferences p = await SharedPreferences.getInstance();
    AppConfig.activeModelId = p.getString(_kModelId) ?? AppConfig.activeModelId;
    AppConfig.modelDir = p.getString(_kModelDir) ?? '';
    AppConfig.modelDirUri = p.getString(_kModelDirUri) ?? '';
    AppConfig.modelPreviewEnabled =
        p.getBool(_kModelPreview) ?? AppConfig.modelPreviewEnabled;
    AppConfig.quality = _enum<StageQuality>(
        StageQuality.values, p.getInt(_kQuality), StageQuality.medium);
    AppConfig.cameraEnabled = p.getBool(_kCamera) ?? AppConfig.cameraEnabled;
    AppConfig.cameraFacing = _enum<CameraSide>(
        CameraSide.values, p.getInt(_kCameraFacing), CameraSide.front);
    AppConfig.autoSendAsr = p.getBool(_kAutoAsr) ?? AppConfig.autoSendAsr;
    AppConfig.characterName = p.getString(_kName) ?? AppConfig.characterName;
    AppConfig.suggestedWsUrl = p.getString(_kLastWsUrl) ?? '';

    final String savedUid = p.getString(_kUid) ?? '';
    AppConfig.uid = DeviceIdentity.normalize(savedUid);
    if (!DeviceIdentity.isValid(savedUid)) {
      await p.setString(_kUid, AppConfig.uid);
    }
    AppConfig.token = p.getString(_kToken) ?? '';

    AppConfig.swipeRightVelocity =
        p.getDouble(_kSwipe) ?? AppConfig.swipeRightVelocity;
    AppConfig.swipeMinDistance =
        p.getDouble(_kSwipeMin) ?? AppConfig.swipeMinDistance;
    AppConfig.poseSendHz = p.getInt(_kPoseHz) ?? AppConfig.poseSendHz;
    AppConfig.poseDeadZoneDeg =
        p.getDouble(_kDeadZone) ?? AppConfig.poseDeadZoneDeg;
    AppConfig.poseLowPassK =
        p.getDouble(_kLowPassK) ?? AppConfig.poseLowPassK;
    AppConfig.peekDelayMs = p.getInt(_kPeekMs) ?? AppConfig.peekDelayMs;
    AppConfig.peekHoldMs = p.getInt(_kPeekHoldMs) ?? AppConfig.peekHoldMs;
    AppConfig.flingDurationMs = p.getInt(_kFlingMs) ?? AppConfig.flingDurationMs;
    AppConfig.returnDurationMs =
        p.getInt(_kReturnMs) ?? AppConfig.returnDurationMs;
    AppConfig.typewriterCps =
        p.getInt(_kTypewriterCps) ?? AppConfig.typewriterCps;
    AppConfig.turnStepDeg = p.getDouble(_kTurnStep) ?? AppConfig.turnStepDeg;
    AppConfig.triggerCooldownMs =
        p.getInt(_kCooldownMs) ?? AppConfig.triggerCooldownMs;
    AppConfig.mirrorTextInput =
        p.getBool(_kMirrorText) ?? AppConfig.mirrorTextInput;
    AppConfig.mirrorAsrText =
        p.getBool(_kMirrorAsr) ?? AppConfig.mirrorAsrText;
    AppConfig.autoReconnect =
        p.getBool(_kAutoReconnect) ?? AppConfig.autoReconnect;
    AppConfig.maxReconnectAttempts =
        p.getInt(_kMaxAttempts) ?? AppConfig.maxReconnectAttempts;

    AppConfig.targetFps =
        (p.getInt(_kTargetFps) ?? AppConfig.targetFps).clamp(1, 144).toInt();
    AppConfig.showFps = p.getBool(_kShowFps) ?? AppConfig.showFps;
    AppConfig.powerSaveEnabled =
        p.getBool(_kPowerSave) ?? AppConfig.powerSaveEnabled;
    AppConfig.overlayEnabled =
        p.getBool(_kOverlay) ?? AppConfig.overlayEnabled;
    AppConfig.asrMode =
        _enum<AsrMode>(AsrMode.values, p.getInt(_kAsrMode), AsrMode.auto);

    AppConfig.scheme =
        _enum<GalScheme>(GalScheme.values, p.getInt(_kScheme), GalScheme.blue);
    GalPalette.scheme.value = AppConfig.scheme;
    AppConfig.reduceAnimations =
        p.getBool(_kReduceAnimations) ?? AppConfig.reduceAnimations;
    AppConfig.disableTypewriter =
        p.getBool(_kDisableTypewriter) ?? AppConfig.disableTypewriter;
    AppConfig.inputDebounceMs =
        (p.getInt(_kInputDebounce) ?? AppConfig.inputDebounceMs)
            .clamp(0, 2000)
            .toInt();
    AppConfig.inputMergeEnabled =
        p.getBool(_kInputMerge) ?? AppConfig.inputMergeEnabled;
    AppConfig.dedupeAdjacent =
        p.getBool(_kDedupe) ?? AppConfig.dedupeAdjacent;
    AppConfig.overlayPeekEnabled =
        p.getBool(_kOverlayPeek) ?? AppConfig.overlayPeekEnabled;
    AppConfig.overlayScale =
        (p.getDouble(_kOverlayScale) ?? AppConfig.overlayScale)
            .clamp(0.3, 1.0)
            .toDouble();

    AppConfig.overlayActive = false;
  }

  static Future<void> saveAll() async {
    final SharedPreferences p = await SharedPreferences.getInstance();
    await p.setString(_kModelId, AppConfig.activeModelId);
    await p.setString(_kModelDir, AppConfig.modelDir);
    await p.setString(_kModelDirUri, AppConfig.modelDirUri);
    await p.setBool(_kModelPreview, AppConfig.modelPreviewEnabled);
    await p.setInt(_kQuality, AppConfig.quality.index);
    await p.setBool(_kCamera, AppConfig.cameraEnabled);
    await p.setInt(_kCameraFacing, AppConfig.cameraFacing.index);
    await p.setBool(_kAutoAsr, AppConfig.autoSendAsr);
    await p.setString(_kName, AppConfig.characterName);
    await p.setString(_kUid, AppConfig.uid);
    await p.setString(_kToken, AppConfig.token);
    await p.setDouble(_kSwipe, AppConfig.swipeRightVelocity);
    await p.setDouble(_kSwipeMin, AppConfig.swipeMinDistance);
    await p.setInt(_kPoseHz, AppConfig.poseSendHz);
    await p.setDouble(_kDeadZone, AppConfig.poseDeadZoneDeg);
    await p.setDouble(_kLowPassK, AppConfig.poseLowPassK);
    await p.setInt(_kPeekMs, AppConfig.peekDelayMs);
    await p.setInt(_kPeekHoldMs, AppConfig.peekHoldMs);
    await p.setInt(_kFlingMs, AppConfig.flingDurationMs);
    await p.setInt(_kReturnMs, AppConfig.returnDurationMs);
    await p.setInt(_kTypewriterCps, AppConfig.typewriterCps);
    await p.setDouble(_kTurnStep, AppConfig.turnStepDeg);
    await p.setInt(_kCooldownMs, AppConfig.triggerCooldownMs);
    await p.setBool(_kMirrorText, AppConfig.mirrorTextInput);
    await p.setBool(_kMirrorAsr, AppConfig.mirrorAsrText);
    await p.setBool(_kAutoReconnect, AppConfig.autoReconnect);
    await p.setInt(_kMaxAttempts, AppConfig.maxReconnectAttempts);
    await p.setInt(_kTargetFps, AppConfig.targetFps);
    await p.setBool(_kShowFps, AppConfig.showFps);
    await p.setBool(_kPowerSave, AppConfig.powerSaveEnabled);
    await p.setBool(_kOverlay, AppConfig.overlayEnabled);
    await p.setInt(_kAsrMode, AppConfig.asrMode.index);
    await p.setInt(_kScheme, AppConfig.scheme.index);
    await p.setBool(_kReduceAnimations, AppConfig.reduceAnimations);
    await p.setBool(_kDisableTypewriter, AppConfig.disableTypewriter);
    await p.setInt(_kInputDebounce, AppConfig.inputDebounceMs);
    await p.setBool(_kInputMerge, AppConfig.inputMergeEnabled);
    await p.setBool(_kDedupe, AppConfig.dedupeAdjacent);
    await p.setBool(_kOverlayPeek, AppConfig.overlayPeekEnabled);
    await p.setDouble(_kOverlayScale, AppConfig.overlayScale);
  }

  /// 高频参数变更（滑杆松手、连续拨开关）用这个：120ms 内的多次调用合并成
  /// 一次 saveAll()，避免每拖一下就全量写 30+ 个 SharedPreferences key。
  /// 需要立即落盘的场景（换 uid、换模型、切色系）仍直接调 saveAll()。
  static Timer? _saveTimer;

  static void scheduleSave() {
    _saveTimer?.cancel();
    _saveTimer = Timer(const Duration(milliseconds: 120), () {
      _saveTimer = null;
      unawaited(saveAll().catchError((Object _) {}));
    });
  }

  static Future<String> resetUid() async {
    final SharedPreferences p = await SharedPreferences.getInstance();
    AppConfig.uid = DeviceIdentity.newUid();
    await p.setString(_kUid, AppConfig.uid);
    return AppConfig.uid;
  }
}
