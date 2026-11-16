import 'dart:async';

import 'package:flutter/foundation.dart';

import '../core/config/app_config.dart';
import '../core/config/model_config.dart';
import '../core/config/model_motion.dart';
import '../core/net/device_identity.dart';
import '../core/net/ws_service.dart';
import '../core/net/ws_url.dart';
import '../core/input/text_merge.dart';
import '../core/sensors/pose_service.dart';
import '../core/stage/orientation_mapper.dart';
import '../core/stage/stage_machine.dart';
import '../core/voice/voice_service.dart';
import '../debug/debug_flags.dart';
import '../services/live2d/live2d_stage.dart';
import '../services/live2d/model_asset_installer.dart';
import '../services/live2d/model_catalog.dart';
import '../services/live2d/model_resources.dart';
import '../services/platform/overlay_channel.dart';
import '../services/platform/permissions.dart';
import '../services/storage/prefs.dart';

/// 文本来源：防抖合并时保留来源，避免打字被当成 ASR 重复镜像。
enum TextSource { typed, asr, systemAsr }

/// 装配层：唯一持有各服务并做事件桥接的地方（应用级单例 SessionHolder.instance）。
class StageSession extends ChangeNotifier {
  StageSession({String wsUrl = '', String pairUid = ''})
      : _wsUrl = wsUrl,
        _pairUid = pairUid;

  static const String kOfflineHint = '离线单机 · 请重试 / 点「设定 → 连接 → 重连」';

  String _wsUrl;
  String _pairUid;
  late final WsService ws = WsService(url: _wsUrl);
  late final StageMachine machine = StageMachine(onEmit: _onStageEmit);
  final OrientationMapper orientation = OrientationMapper();
  late final PoseService pose = PoseService(onPose: _onPose);
  late final VoiceService voice = VoiceService(
    onChunk: _onAudioChunk,
    onState: _onVoiceState,
    onText: (String m) => hint.value = m,
    onSystemText: _onSystemAsrText,
  );
  late final Live2DStage live2d = Live2DStage(onChanged: _onLive2DChanged);

  void _onLive2DChanged() {
    if (_disposed) return;
    // controller 一创建就刷新，让 CharacterLayer 立刻挂上 Live2DView，
    // 插件的 whenAttached 才能在超时前完成，模型才真正加载。
    //
    // 只递增 modelRevision：原来这里同时递增 visualRevision 并
    // notifyListeners()，会把舞台 / 设置页整棵树都重建一遍，
    // 刷新模型时用户就会看到「页面一闪而过」。
    modelRevision.value++;
  }

  final ValueNotifier<int> stageRevision = ValueNotifier<int>(0);
  final ValueNotifier<String> dialogText = ValueNotifier<String>('');
  final ValueNotifier<bool> recording = ValueNotifier<bool>(false);
  final ValueNotifier<double> turnDeg = ValueNotifier<double>(0);
  final ValueNotifier<String> hint = ValueNotifier<String>(kOfflineHint);
  final ValueNotifier<bool> powerSave = ValueNotifier<bool>(false);
  /// 面板被拖到右侧隐藏时进入「静态省电」（停帧，但展开即恢复）。
  final ValueNotifier<bool> staticMode = ValueNotifier<bool>(false);
  final ValueNotifier<double> fps = ValueNotifier<double>(0);
  final ValueNotifier<bool> overlayOn = ValueNotifier<bool>(false);
  /// 背景 / 相机 / 对话框的显式刷新信号：开关、档位、前后置、色系、
  /// 换模、减少动画等变更都递增它，避免依赖「碰巧被重建」的隐式链路。
  final ValueNotifier<int> visualRevision = ValueNotifier<int>(0);
  /// Live2D controller / ready / 降级原因变化：只有立绘层与状态条订阅。
  /// 与 visualRevision 分开，模型刷新不再带动背景 / 对话框 / 设置页整树重建。
  final ValueNotifier<int> modelRevision = ValueNotifier<int>(0);
  final List<String> history = <String>[];

  bool mockMode = bool.fromEnvironment('STAGE_MOCK');
  void Function(String action, Map<String, dynamic> params)? onInject;

  bool _paused = false;
  bool _started = false;
  bool _streaming = false;
  bool _reloading = false;
  bool _sendRecordFrames = true;
  String _lastSent = '';
  bool _disposed = false;

  // ---- 输入防抖合并 ----
  Timer? _inputTimer;
  String _inputBuffer = '';
  TextSource _bufferSource = TextSource.typed;

  // ---- 隐藏面板 → 静态省电 ----
  final Set<String> _hiddenPanels = <String>{};

  void configureEndpoint(String wsUrl, String pairUid) {
    final bool changed = _started && wsUrl.isNotEmpty && wsUrl != _wsUrl;
    _wsUrl = wsUrl;
    _pairUid = pairUid;
    // 从连接页重新进入舞台（pushReplacementNamed(stage)）时，
    // 原来 `_started` 直接 return，新地址永远进不了 WsService。
    if (changed) {
      AppConfig.wsUrl = wsUrl;
      AppConfig.suggestedWsUrl = wsUrl;
      ws.updateUrl(wsUrl, force: true);
      unawaited(Prefs.setLastWsUrl(wsUrl));
    }
  }

  AsrEngine get effectiveAsrEngine {
    switch (AppConfig.asrMode) {
      case AsrMode.system:
        return AsrEngine.system;
      case AsrMode.server:
        return AsrEngine.server;
      case AsrMode.auto:
        return (!mockMode && ws.isReady) ? AsrEngine.server : AsrEngine.system;
    }
  }

  String get asrEngineLabel {
    switch (effectiveAsrEngine) {
      case AsrEngine.system:
        return '系统内置识别（离线可用）';
      case AsrEngine.server:
        return '服务端识别（需连接电脑端）';
    }
  }

  Future<void> start() async {
    if (_started) return;
    _started = true;
    await Prefs.ensureLoaded();
    history
      ..clear()
      ..addAll(await Prefs.loadHistory());

    // 重启恢复：目录清单只在设置页扫描时注入过，进程重启后 catalog 为空，
    // `ModelConfig.byId()` 会把用户上次选的目录模型回退成占位（模型「不加载」的根因之一）。
    // 按持久化的目录自动重建清单，再解析 activeModelId。
    if (AppConfig.modelDir.isNotEmpty) {
      try {
        await ModelCatalog.refresh(AppConfig.modelDir);
      } catch (_) {
        // 目录被删 / 无权限时保持占位，不阻断启动
      }
    } else if (AppConfig.modelDirUri.isNotEmpty) {
      hint.value = '上次关联的是系统目录 URI，请到「设定 → 模型」重新选择一次目录';
    }

    // 旧版本用 path.hashCode 当 id，重启后不保证一致：迁移到第一个可用
    // 目录模型并写回，避免「上次选过模型，重启就不显示」。
    final String resolved = ModelCatalog.resolveSavedId(AppConfig.activeModelId);
    if (resolved != AppConfig.activeModelId) {
      AppConfig.activeModelId = resolved;
      await Prefs.saveAll();
    }

    AppConfig.wsUrl = _wsUrl;
    if (_wsUrl.isNotEmpty) {
      AppConfig.suggestedWsUrl = _wsUrl;
      await Prefs.setLastWsUrl(_wsUrl);
    }
    if (_pairUid.isNotEmpty && DeviceIdentity.isValid(_pairUid)) {
      AppConfig.uid = _pairUid;
      await Prefs.saveAll();
    }
    ws.setIdentity(AppConfig.uid, device: AppConfig.device, token: AppConfig.token);

    ws.onStateChanged = (WsState s) {
      hint.value = switch (s) {
        WsState.connected => '已连接 · 正在绑定身份…',
        WsState.reconnecting => '连接中断，正在重试…请稍候',
        WsState.connecting => '连接中…',
        WsState.offline => kOfflineHint,
      };
      notifyListeners();
    };
    ws.onRegisterResult = (bool ok, String uid, String message) {
      if (ok) {
        AppConfig.uid = uid;
        hint.value = '绑定成功 · ${_shortUid(uid)}';
        if (!mockMode) ws.sendSnapshot(machine.snapshotName, machine.seq);
      } else {
        hint.value = '绑定失败，请重试：$message';
      }
      notifyListeners();
    };
    ws.onStageAction = _onRemoteAction;
    ws.onChatText = _pushDialog;
    ws.onStreamDelta = _onStreamDelta;
    ws.onAsrText = _onAsrText;
    ws.onError = (String m) => hint.value = '$m · 请重试';
    if (kStageDebug) ws.onFrameLog = _debugFrameLog;

    // Live2DStage 内建 attach 超时，这里不会再无限阻塞；
    // 即使模型加载失败，pose / WebSocket / 相机链路也必须继续启动。
    await live2d.setModel(AppConfig.activeModel);
    if (!live2d.ready) {
      hint.value = live2d.degradationReason ??
          '模型未加载 · 请到「设定 → 模型」选模型或选择目录';
    }
    pose.setHz(AppConfig.poseSendHz);
    await pose.start();
    ws.connect();
    visualRevision.value++;
    notifyListeners();
  }

  static String _shortUid(String uid) =>
      uid.length > 12 ? '${uid.substring(0, 12)}…' : uid;

  static double _asDouble(dynamic v) {
    if (v is num) return v.toDouble();
    return double.tryParse(v?.toString() ?? '') ?? 0.0;
  }

  void _onStageEmit(StageIntent intent) {
    if (!mockMode && ws.isReady) {
      ws.sendStage(intent.action, params: intent.params, seq: intent.seq);
    }
    stageRevision.value++;
  }

  void _onRemoteAction(String action, Map<String, dynamic> data) {
    if (mockMode) return;
    if (action == 'model_set') {
      final String id = (data['model_id'] ?? '').toString();
      if (id.isNotEmpty) {
        changeModel(id, (data['model_path'] ?? '').toString(), notifyPeer: false);
      }
      return;
    }
    if (action == 'play_animation') {
      final String key =
          (data['group'] ?? data['name'] ?? data['motion'] ?? '').toString();
      if (key.isNotEmpty) live2d.play(key);
      return;
    }
    if (action == 'turn' || action == 'turn_left' || action == 'turn_right') {
      final Map<String, dynamic> params = data['params'] is Map
          ? Map<String, dynamic>.from(data['params'] as Map)
          : <String, dynamic>{};
      double deg = _asDouble(data['deg'] ?? params['deg']);
      if (deg == 0 && action != 'turn') deg = AppConfig.turnStepDeg;
      if (action == 'turn_left' && deg > 0) deg = -deg;
      turnDeg.value = (turnDeg.value + deg).clamp(-30.0, 30.0).toDouble();
      return;
    }
    final int seq = (data['seq'] is int) ? data['seq'] as int : 0;
    final int epoch = (data['epoch'] is int) ? data['epoch'] as int : 0;
    machine.remoteAction(
      action,
      seq,
      epoch: epoch,
      fromId: (data['from_id'] ?? '').toString(),
    );
    stageRevision.value++;
  }

  void _onPose(double a, double b, double g, int t) {
    if (_paused || mockMode || powerSave.value || staticMode.value) return;
    turnDeg.value = orientation.map(a, b, g).turnDeg;
    if (ws.isReady) ws.sendPose(a, b, g, t);
  }

  void _onAudioChunk(String base64, bool isFinal) {
    if (mockMode || !ws.isReady) return;
    ws.sendAudioChunk(base64, isFinal);
  }

  void _onVoiceState(bool v) {
    recording.value = v;
    if (_sendRecordFrames && !mockMode && ws.isReady) {
      if (v) {
        ws.sendRecordStart();
      } else {
        ws.sendRecordStop();
      }
    }
  }

  void _onAsrText(String text) {
    if (text.isEmpty) return;
    hint.value = '识别：$text';
    submitText(text, source: TextSource.asr);
  }

  void _onSystemAsrText(String text) => submitText(text, source: TextSource.systemAsr);

  void _onStreamDelta(String delta) {
    if (!_streaming) {
      _streaming = true;
      dialogText.value = '';
    }
    final String next = dialogText.value + delta;
    dialogText.value = next.length > AppConfig.maxTextLength * 2
        ? next.substring(next.length - AppConfig.maxTextLength)
        : next;
  }

  void _pushDialog(String text) {
    if (text.isEmpty) return;
    _streaming = false;
    _remember(text);
    dialogText.value = text;
  }

  /// 历史相邻去重：同一句连续出现只留一条。
  void _remember(String text) {
    if (text.isEmpty) return;
    if (AppConfig.dedupeAdjacent &&
        history.isNotEmpty &&
        history.last == text) {
      return;
    }
    history.add(text);
    if (history.length > AppConfig.maxHistoryItems) history.removeAt(0);
    Prefs.scheduleHistorySave(history);
  }

  /// 清空历史（设置页 / 历史页共用），同时落盘，重启不会又冒出来。
  void clearHistory() {
    history.clear();
    Prefs.scheduleHistorySave(history);
    hint.value = '历史已清空 · 请重试';
    notifyListeners();
  }

  // ---- 输入：防抖合并 + 相邻去重 ----

  /// 短时间内的连续提交（逐字 / ASR 中间结果 / 连点发送）合并为一条；
  /// 前缀关系取最长（增量输入），否则换行拼接；与上一条相同则直接丢弃。
  void submitText(
    String raw, {
    TextSource source = TextSource.typed,
    bool immediate = false,
  }) {
    final String t = raw.trim();
    if (t.isEmpty || t.length > AppConfig.maxTextLength) return;
    if (immediate ||
        AppConfig.inputDebounceMs <= 0 ||
        !AppConfig.inputMergeEnabled) {
      _inputTimer?.cancel();
      _inputTimer = null;
      _inputBuffer = '';
      _deliver(t, source);
      return;
    }
    _bufferSource = source;
    _inputBuffer = mergeTextInput(_inputBuffer, t);
    _inputTimer?.cancel();
    _inputTimer = Timer(
      Duration(milliseconds: AppConfig.inputDebounceMs),
      _flushInput,
    );
  }

  void _flushInput() {
    _inputTimer = null;
    final String t = _inputBuffer.trim();
    final TextSource source = _bufferSource;
    _inputBuffer = '';
    if (t.isNotEmpty) _deliver(t, source);
  }

  /// 页面离开 / 主动发送时立刻落地，避免防抖窗口里丢消息。
  void flushInput() {
    _inputTimer?.cancel();
    _inputTimer = null;
    _flushInput();
  }

  void _deliver(String text, TextSource source) {
    if (_disposed) return;
    final String t = text.trim();
    if (t.isEmpty || t.length > AppConfig.maxTextLength) return;
    if (AppConfig.dedupeAdjacent &&
        isAdjacentDuplicate(
            t, history.isNotEmpty ? history.last : '', _lastSent)) {
      hint.value = '已合并重复输入';
      notifyListeners();
      return;
    }
    _lastSent = t;
    _remember(t);
    final bool online = !mockMode && ws.isReady;
    if (online) {
      _streaming = false;
      dialogText.value = '';
      if (source == TextSource.typed && AppConfig.mirrorTextInput) {
        ws.sendTextInput(t);
      }
      if (source != TextSource.typed &&
          !AppConfig.autoSendAsr &&
          AppConfig.mirrorAsrText) {
        ws.sendAsrText(t);
      } else {
        ws.sendChat(t, source: source == TextSource.typed ? 'text' : 'asr');
      }
      hint.value = source == TextSource.typed ? '已发送' : '识别：$t';
    } else {
      dialogText.value = t;
      hint.value = mockMode
          ? '调试模式：未发送'
          : '离线 · '
              '${source == TextSource.systemAsr ? '系统识别' : '识别'}：$t · 请重试连接';
    }
    notifyListeners();
  }

  /// 兼容旧调用点。
  void sendText(String text) => submitText(text);

  void retryLast() {
    final String last = _lastSent.isNotEmpty
        ? _lastSent
        : (history.isNotEmpty ? history.last : '');
    if (last.isEmpty) {
      hint.value = '没有可重试的消息，请重试输入';
      notifyListeners();
      return;
    }
    submitText(last, immediate: true);
  }

  /// 重新加载当前模型；rescanAssets=true 时清掉内置资源安装缓存重新自检。
  /// 全程只更新 modelRevision / hint，不再递增 visualRevision、不再
  /// notifyListeners() 整树广播 —— 这是「点刷新 → 页面一闪而过」的直接修复。
  Future<void> reloadModel({bool rescanAssets = false}) async {
    if (_reloading || _disposed) return;
    _reloading = true;
    try {
      if (rescanAssets) {
        ModelAssetInstaller.invalidate();
        ModelResources.invalidate();
      }
      await live2d.setModel(AppConfig.activeModel, force: true);
      hint.value = live2d.ready ? live2d.statusText : live2d.detailText;
      modelRevision.value++;
    } finally {
      _reloading = false;
    }
  }

  Future<void> changeModel(
    String id,
    String path, {
    bool notifyPeer = true,
  }) async {
    if (_reloading || _disposed) return;
    _reloading = true;
    try {
      // 远端 model_set 可能带一个本地清单里没有的 id/path：注册为临时模型。
      // 原来 byId 会回退占位，导致「电脑端换模」永远不生效。
      // 若只给了未知 id、没带路径，就不要把 activeModelId 写成无效值，
      // 否则本机模型被悄悄换掉、重启后还回退成占位立绘。
      if (id.isNotEmpty && !ModelConfig.isValidId(id)) {
        if (path.isEmpty) {
          hint.value = '远端指定的模型不在本机清单里且没带路径 · '
              '请重试或到「设定 → 模型」选择';
          return;
        }
        ModelConfig.registerExternal(id, path);
      }
      AppConfig.activeModelId = id;
      await Prefs.saveAll();
      ModelResources.invalidate(id);
      await live2d.setModel(AppConfig.activeModel, force: true);
      if (notifyPeer && !mockMode && ws.isReady) ws.sendModelSet(id, path);
      if (overlayOn.value) await refreshOverlayAppearance();
      hint.value = live2d.ready ? live2d.statusText : live2d.detailText;
      modelRevision.value++;
      // 低频操作：状态栏模型名需要跟着换，才保留一次全局通知。
      notifyListeners();
    } finally {
      _reloading = false;
    }
  }

  /// 动作组快捷试播（设定 → 动画）。
  Future<void> playGroup(String group) async {
    if (_disposed) return;
    final bool ok = live2d.playGroup(group);
    hint.value = ok
        ? '已下发动作组：$group'
        : '模型未就绪 · 请先加载模型再试播动作组';
  }

  /// 点选某个内置动画预览。仅入口声明过的动作有组名可精确点播；
  /// 目录里直接扫到的文件用文件名兜底请求，并如实告诉用户原因。
  Future<void> playMotion(ModelMotion m) async {
    if (_disposed) return;
    final String group = m.group.isNotEmpty ? m.group : m.name;
    final bool ok = live2d.playGroup(group);
    if (!ok) {
      hint.value = '模型未就绪 · 请先到「设定 → 模型」加载模型再预览演出';
      return;
    }
    hint.value = m.playable
        ? '演出：${m.name}（${m.group} · ${m.durationLabel}）'
        : '已请求演出「${m.name}」· 该动画未在入口声明动作组，'
            '补齐 .model3.json 的 Motions 后可精确点播';
  }

  Future<void> reconnect(String rawUrl) async {
    final WsEndpoint? endpoint = WsUrl.parse(rawUrl);
    if (endpoint == null) {
      hint.value = '地址格式无效，请重试';
      notifyListeners();
      return;
    }
    if (endpoint.hasUid) {
      AppConfig.uid = endpoint.uid;
      await Prefs.saveAll();
      ws.setIdentity(AppConfig.uid, device: AppConfig.device, token: AppConfig.token);
    }
    AppConfig.wsUrl = endpoint.url;
    AppConfig.suggestedWsUrl = endpoint.url;
    await Prefs.setLastWsUrl(endpoint.url);
    ws.updateUrl(endpoint.url, force: true);
    hint.value = '正在重连…';
    notifyListeners();
  }

  void applyParams() {
    pose.setHz(AppConfig.poseSendHz);
    // 相机开关 / 前后置 / 性能档位 / 逐字机开关 / 减少动画都走这里，
    // 显式递增让背景层与对话框立即重建，不再依赖「碰巧被 rebuild」。
    visualRevision.value++;
    notifyListeners();
  }

  Future<void> resetIdentity() async {
    final String uid = await Prefs.resetUid();
    ws.setIdentity(uid, device: AppConfig.device, token: AppConfig.token);
    if (ws.isReady) ws.sendRegister();
    hint.value = '已重新绑定 · ${_shortUid(uid)}';
    notifyListeners();
  }

  // ---- 语音按钮：点按切换 / 长按共用 ----

  Future<void> startVoice() async {
    final AsrEngine engine = effectiveAsrEngine;
    _sendRecordFrames = engine == AsrEngine.server;
    await voice.start(engine: engine);
  }

  Future<void> stopVoice() => voice.stop();

  Future<void> toggleVoice() async {
    if (voice.isRecording) {
      await stopVoice();
    } else {
      await startVoice();
    }
  }

  // ---- 帧率 / 省电 / 置顶 ----

  /// 任一面板被拖到右侧隐藏 → 静态省电；全部展开 → 恢复。
  void setPanelHidden(String id, bool hidden) {
    if (_disposed) return;
    if (hidden) {
      _hiddenPanels.add(id);
    } else {
      _hiddenPanels.remove(id);
    }
    final bool next = _hiddenPanels.isNotEmpty;
    // ValueNotifier.value 自己会通知监听者，这里不再额外 notifyListeners()，
    // 避免面板在 dispose 阶段回调时触发整棵树 rebuild。
    if (staticMode.value != next) staticMode.value = next;
  }

  /// 舞台页退出时清空面板标记，否则再进页面会一直停在「静态省电」。
  void clearPanelFlags() {
    _hiddenPanels.clear();
    if (staticMode.value) staticMode.value = false;
  }

  void setPowerSave(bool value) {
    if (powerSave.value == value) return;
    powerSave.value = value;
    setPaused(value);
    notifyListeners();
  }

  Future<bool> startOverlay() async {
    if (!AppConfig.overlayEnabled) return false;
    if (!await OverlayChannel.available()) {
      hint.value = '此平台不支持置顶浮窗，请重试或关闭该选项';
      notifyListeners();
      return false;
    }
    if (!await Permissions.overlay() || !await OverlayChannel.canDraw()) {
      hint.value = '需要「显示在其他应用上层」权限，请重试';
      notifyListeners();
      return false;
    }
    final bool ok = await OverlayChannel.start(
      AppConfig.activeModel.name,
      scheme: AppConfig.scheme.name,
      scale: AppConfig.overlayScale,
    );
    AppConfig.overlayActive = ok;
    overlayOn.value = ok;
    if (ok && AppConfig.overlayPeekEnabled) {
      // 置顶时缩小在右侧 + 默认右侧探头，避免遮挡又保留模型可见。
      machine.enterOverlayPeek();
      stageRevision.value++;
    }
    hint.value = ok ? '置顶浮窗已开启 · 右侧探头' : '浮窗启动失败，请重试';
    notifyListeners();
    return ok;
  }

  Future<void> stopOverlay({bool silent = false}) async {
    await OverlayChannel.stop();
    AppConfig.overlayActive = false;
    overlayOn.value = false;
    if (machine.state == StageState.peekBack) {
      machine.exitOverlayPeek();
      stageRevision.value++;
    }
    if (!silent && !_disposed) notifyListeners();
  }

  /// 切换色系 / 换模 / 调缩放后同步原生浮窗外观。
  Future<void> refreshOverlayAppearance() async {
    if (!overlayOn.value) return;
    await OverlayChannel.updateAppearance(
      name: AppConfig.activeModel.name,
      scheme: AppConfig.scheme.name,
      scale: AppConfig.overlayScale,
    );
  }

  void triggerFling(double velocity) {
    machine.flingOut(velocity: velocity);
    stageRevision.value++;
  }

  void turn(double deg) => machine.turn(deg);

  void inject(String action, [Map<String, dynamic>? params]) {
    mockMode = true;
    switch (action) {
      case 'fling_out':
        triggerFling(1200);
        break;
      case 'peek_back':
        machine.peekBack();
        stageRevision.value++;
        break;
      case 'return_idle':
        machine.returnIdle();
        stageRevision.value++;
        break;
      case 'jump_out':
        machine.remoteAction('jump_out', -1);
        stageRevision.value++;
        break;
      case 'turn_left':
      case 'turn_right':
        turn(action == 'turn_left' ? -18 : 18);
        break;
      case 'asr':
        _onSystemAsrText('（模拟识别文本）');
        break;
      case 'delta':
        dialogText.value = dialogText.value + '（模拟流式）';
        break;
      default:
        break;
    }
    onInject?.call(action, params ?? <String, dynamic>{});
  }

  void setPaused(bool value) {
    _paused = value;
    if (value) {
      pose.pause();
      live2d.pause();
    } else {
      pose.resume();
      live2d.resume();
    }
  }

  void _debugFrameLog(String direction, String type, int bytes) {
    onFrameTap?.call(direction, type, bytes);
  }

  void Function(String direction, String type, int bytes)? onFrameTap;

  Future<void> dispose() async {
    if (_disposed) return;
    _disposed = true;
    _inputTimer?.cancel();
    _inputTimer = null;
    // App 退出时不再落地防抖缓冲：此时网络已不可用，且 _deliver 里的
    // notifyListeners() 会在 dispose 阶段触发监听者 rebuild。
    _inputBuffer = '';
    await stopOverlay(silent: true);
    // 防抖窗口里没落盘的设置 / 历史补写，避免退出丢数据。
    await Prefs.flush();
    await pose.dispose();
    await voice.dispose();
    await ws.dispose();
    live2d.dispose();
    stageRevision.dispose();
    dialogText.dispose();
    recording.dispose();
    turnDeg.dispose();
    hint.dispose();
    powerSave.dispose();
    staticMode.dispose();
    fps.dispose();
    overlayOn.dispose();
    visualRevision.dispose();
    modelRevision.dispose();
    onInject = null;
    onFrameTap = null;
    super.dispose();
  }
}
