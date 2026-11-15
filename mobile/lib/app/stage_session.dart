import 'package:flutter/foundation.dart';

import '../core/config/app_config.dart';
import '../core/net/ws_service.dart';
import '../core/sensors/pose_service.dart';
import '../core/stage/orientation_mapper.dart';
import '../core/stage/stage_machine.dart';
import '../core/voice/voice_service.dart';
import '../debug/debug_flags.dart';
import '../services/live2d/live2d_stage.dart';
import '../services/storage/prefs.dart';

/// 装配层：唯一持有各服务并做事件桥接的地方。
/// pages 只把它塞进 StageScope，components 只读它，不碰网络实现。
class StageSession extends ChangeNotifier {
  StageSession({required String wsUrl}) : _wsUrl = wsUrl;

  final String _wsUrl;
  late final WsService ws = WsService(url: _wsUrl);
  late final StageMachine machine = StageMachine(onEmit: _onStageEmit);
  final OrientationMapper orientation = OrientationMapper();
  late final PoseService pose = PoseService(onPose: _onPose);
  late final VoiceService voice = VoiceService(
    onChunk: _onAudioChunk,
    onState: (bool v) {
      recording.value = v;
      if (!mockMode && ws.isReady) {
        if (v) {
          ws.sendRecordStart();
        } else {
          ws.sendRecordStop();
        }
      }
    },
    onText: (String m) => hint.value = m,
  );
  final Live2DStage live2d = Live2DStage();

  final ValueNotifier<int> stageRevision = ValueNotifier<int>(0);
  final ValueNotifier<String> dialogText = ValueNotifier<String>('');
  final ValueNotifier<bool> recording = ValueNotifier<bool>(false);
  final ValueNotifier<double> turnDeg = ValueNotifier<double>(0);
  final ValueNotifier<String> hint = ValueNotifier<String>('');
  final List<String> history = <String>[];

  /// mock 开启时屏蔽真实入站舞台帧，避免两套源同时驱动状态机。
  bool mockMode = bool.fromEnvironment('STAGE_MOCK');

  /// 调试注入回调（由 debug/ 在编译期分支里绑定）。
  void Function(String action, Map<String, dynamic> params)? onInject;

  bool _paused = false;
  bool _started = false;

  Future<void> start() async {
    if (_started) return;
    _started = true;
    await Prefs.loadAll();

    ws.onStateChanged = (WsState s) {
      hint.value = switch (s) {
        WsState.connected => '已连接',
        WsState.reconnecting => '重连中…',
        WsState.connecting => '连接中…',
        WsState.offline => '离线（可单机演出）',
      };
      notifyListeners();
    };
    ws.onStageAction = _onRemoteAction;
    ws.onChatText = _pushDialog;
    ws.onStreamDelta = (String d) => dialogText.value = dialogText.value + d;
    ws.onAsrText = _onAsrText;
    ws.onError = (String m) => hint.value = m;
    if (kStageDebug) {
      ws.onFrameLog = _debugFrameLog;
    }

    await live2d.setModel(AppConfig.activeModel);
    await pose.start();
    if (_wsUrl.isNotEmpty) ws.connect();
    notifyListeners();
  }

  void _onStageEmit(StageIntent intent) {
    if (!mockMode && ws.isReady) {
      ws.sendStage(intent.action, params: intent.params, seq: intent.seq);
    }
    stageRevision.value++;
  }

  void _onRemoteAction(String action, Map<String, dynamic> data) {
    if (mockMode) return;
    final int seq = (data['seq'] is int) ? data['seq'] as int : 0;
    machine.remoteAction(action, seq);
    stageRevision.value++;
  }

  void _onPose(double a, double b, double g, int t) {
    if (_paused || mockMode) return;
    turnDeg.value = orientation.map(a, b, g).turnDeg;
    if (ws.isReady) ws.sendPose(a, b, g, t);
  }

  void _onAudioChunk(String base64, bool isFinal) {
    if (mockMode || !ws.isReady) return;
    ws.sendAudioChunk(base64, isFinal);
  }

  void _onAsrText(String text) {
    if (text.isEmpty) return;
    hint.value = '识别：$text';
    if (AppConfig.autoSendAsr) ws.sendChat(text, source: 'asr');
  }

  void _pushDialog(String text) {
    if (text.isEmpty) return;
    _remember(text);
    dialogText.value = text;
  }

  void _remember(String text) {
    history.add(text);
    if (history.length > AppConfig.maxHistoryItems) history.removeAt(0);
  }

  void sendText(String text) {
    final String t = text.trim();
    if (t.isEmpty || t.length > AppConfig.maxTextLength) return;
    _remember(t);
    if (!mockMode && ws.isReady) ws.sendChat(t);
    hint.value = mockMode ? '调试模式：未发送' : '已发送';
  }

  void triggerFling(double velocity) {
    machine.flingOut(velocity: velocity);
    stageRevision.value++;
  }

  void turn(double deg) => machine.turn(deg);

  Future<void> changeModel(String id, String path) async {
    AppConfig.activeModelId = id;
    await Prefs.saveAll();
    await live2d.setModel(AppConfig.activeModel);
    if (!mockMode && ws.isReady) ws.sendModelSet(id, path);
    notifyListeners();
  }

  /// F01：离线/调试注入走同一状态机，只是不发网络帧。
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
        _onAsrText('（模拟识别文本）');
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
    // 由 debug/ 在编译期分支里替换成 DebugBus 记录；此处只保留回调形态，
    // core 与业务层不 import debug/* 实现。
    onFrameTap?.call(direction, type, bytes);
  }

  void Function(String direction, String type, int bytes)? onFrameTap;

  Future<void> dispose() async {
    // S7.5 固定逆序：Pose -> Voice -> WS -> Live2D
    await pose.dispose();
    await voice.dispose();
    await ws.dispose();
    live2d.dispose();
    stageRevision.dispose();
    dialogText.dispose();
    recording.dispose();
    turnDeg.dispose();
    hint.dispose();
    super.dispose();
  }
}
