import 'dart:async';
import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../../app/gal_palette.dart';
import '../../core/config/app_config.dart';
import '../../core/net/device_identity.dart';
import 'history_codec.dart';

/// 本地持久化：只在设置变更/启动时读写，禁止每帧访问（S7.5）。
///
/// 本轮补强：
/// * `ensureLoaded()` 在 runApp 之前一次性读完，避免启动后色系/配置突变
///   触发 MaterialApp 整树重建（页面「闪一下」的来源之一）；
/// * `saveAll()` 用配置快照去重，滑杆防抖期间重复调用不会反复写 30+ 个 key；
/// * 退出时 `flush()` 把防抖窗口里未落盘的改动补写，不再丢最后一次设置；
/// * 对话历史有界持久化，重启不丢，坏数据自动兜底。
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
  static const String _kHistory = 'chat_history_v1';

  static bool _loaded = false;
  static String _lastSnapshot = '';

  static Future<String?> getLastWsUrl() async =>
      (await SharedPreferences.getInstance()).getString(_kLastWsUrl);

  static Future<void> setLastWsUrl(String url) async =>
      (await SharedPreferences.getInstance()).setString(_kLastWsUrl, url);

  static T _enum<T>(List<T> values, int? index, T fallback) =>
      (index != null && index >= 0 && index < values.length)
          ? values[index]
          : fallback;

  /// 配置快照：只在内容真的变了才全量写盘（存储管理）。
  static String _snapshot() => json.encode(<String, dynamic>{
        'modelId': AppConfig.activeModelId,
        'modelDir': AppConfig.modelDir,
        'modelDirUri': AppConfig.modelDirUri,
        'modelPreview': AppConfig.modelPreviewEnabled,
        'quality': AppConfig.quality.index,
        'camera': AppConfig.cameraEnabled,
        'cameraFacing': AppConfig.cameraFacing.index,
        'autoAsr': AppConfig.autoSendAsr,
        'name': AppConfig.characterName,
        'uid': AppConfig.uid,
        'token': AppConfig.token,
        'swipe': AppConfig.swipeRightVelocity,
        'swipeMin': AppConfig.swipeMinDistance,
        'poseHz': AppConfig.poseSendHz,
        'deadZone': AppConfig.poseDeadZoneDeg,
        'lowPassK': AppConfig.poseLowPassK,
        'peekMs': AppConfig.peekDelayMs,
        'peekHoldMs': AppConfig.peekHoldMs,
        'flingMs': AppConfig.flingDurationMs,
        'returnMs': AppConfig.returnDurationMs,
        'typewriterCps': AppConfig.typewriterCps,
        'turnStep': AppConfig.turnStepDeg,
        'cooldownMs': AppConfig.triggerCooldownMs,
        'mirrorText': AppConfig.mirrorTextInput,
        'mirrorAsr': AppConfig.mirrorAsrText,
        'autoReconnect': AppConfig.autoReconnect,
        'maxAttempts': AppConfig.maxReconnectAttempts,
        'targetFps': AppConfig.targetFps,
        'showFps': AppConfig.showFps,
        'powerSave': AppConfig.powerSaveEnabled,
        'overlay': AppConfig.overlayEnabled,
        'asrMode': AppConfig.asrMode.index,
        'scheme': AppConfig.scheme.index,
        'reduceAnimations': AppConfig.reduceAnimations,
        'disableTypewriter': AppConfig.disableTypewriter,
        'inputDebounce': AppConfig.inputDebounceMs,
        'inputMerge': AppConfig.inputMergeEnabled,
        'dedupe': AppConfig.dedupeAdjacent,
        'overlayPeek': AppConfig.overlayPeekEnabled,
        'overlayScale': AppConfig.overlayScale,
      });

  /// 启动前调用一次；`StageSession.start()` 再调也只会命中缓存。
  static Future<void> ensureLoaded() async {
    if (_loaded) return;
    await loadAll();
  }

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
    _loaded = true;
    _lastSnapshot = _snapshot();
  }

  static Future<void> saveAll() async {
    final String snap = _snapshot();
    if (_loaded && snap == _lastSnapshot) return;
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
    _lastSnapshot = snap;
  }

  /// 高频参数变更（滑杆松手、连续拨开关）用这个：120ms 内的多次调用合并成
  /// 一次 saveAll()，避免每拖一下就全量写 30+ 个 SharedPreferences key。
  static Timer? _saveTimer;

  static void scheduleSave() {
    _saveTimer?.cancel();
    _saveTimer = Timer(const Duration(milliseconds: 120), () {
      _saveTimer = null;
      unawaited(saveAll().catchError((Object _) {}));
    });
  }

  /// 退出 /  detached 时补写防抖窗口里的改动，避免丢设置。
  static Future<void> flush() async {
    _saveTimer?.cancel();
    _saveTimer = null;
    try {
      await saveAll();
    } catch (_) {}
    try {
      await flushHistory();
    } catch (_) {}
  }

  static Future<String> resetUid() async {
    final SharedPreferences p = await SharedPreferences.getInstance();
    AppConfig.uid = DeviceIdentity.newUid();
    await p.setString(_kUid, AppConfig.uid);
    // uid 已直接落盘，但快照要同步，后续 saveAll 不会因此重复写全量。
    _lastSnapshot = _snapshot();
    return AppConfig.uid;
  }

  // ---- 对话历史（有界持久化） ----

  static Timer? _historyTimer;
  static List<String>? _pendingHistory;

  static Future<List<String>> loadHistory() async {
    final SharedPreferences p = await SharedPreferences.getInstance();
    return HistoryCodec.decode(
      p.getString(_kHistory),
      limit: AppConfig.maxHistoryItems,
    );
  }

  static Future<void> saveHistory(List<String> items) async {
    _pendingHistory = null;
    final SharedPreferences p = await SharedPreferences.getInstance();
    await p.setString(
      _kHistory,
      HistoryCodec.encode(items, limit: AppConfig.maxHistoryItems),
    );
  }

  static void scheduleHistorySave(List<String> items) {
    _pendingHistory = List<String>.from(items);
    _historyTimer?.cancel();
    _historyTimer = Timer(const Duration(milliseconds: 250), () {
      _historyTimer = null;
      final List<String> snapshot = _pendingHistory ?? const <String>[];
      unawaited(saveHistory(snapshot).catchError((Object _) {}));
    });
  }

  static Future<void> flushHistory() async {
    _historyTimer?.cancel();
    _historyTimer = null;
    final List<String>? items = _pendingHistory;
    if (items == null) return;
    await saveHistory(items);
  }
}
