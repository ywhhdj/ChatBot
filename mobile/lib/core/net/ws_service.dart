import 'dart:async';
import 'dart:math' as math;

import 'package:web_socket_channel/status.dart' as ws_status;
import 'package:web_socket_channel/web_socket_channel.dart';

import '../config/app_config.dart';
import 'device_identity.dart';
import 'ws_events.dart';
import 'ws_frame.dart';

enum WsState { offline, connecting, connected, reconnecting }

/// 唯一通信出口（三端之一）：CONNECT → REGISTER → device.hello → 业务帧。
///
/// * REGISTER 是 CONTROL_EVENTS 首帧，不带 client_id；注册失败不切断连接，可重试；
/// * 打字 / ASR 文本走 device.text_input / device.asr_text 实时送电脑端；
/// * 离线（扫码跳过）不空转重连；设定页点「重连」再 updateUrl + connect；
/// * 所有连接代次带 generation 令牌，旧 socket 的 onDone/onError 不会把新连接踢掉；
/// * 待发队列 / 重连次数 / 回调引用都有界，dispose 时全部释放；
/// * 终态文本（pipeline.final_text）覆盖台词而不是追加，音频回执不当文本。
class WsService {
  WsService({
    required String url,
    String uid = '',
    String device = DeviceIdentity.mobile,
    String token = '',
  })  : _url = url,
        _uid = uid,
        _device = device,
        _token = token;

  String _url;
  String _uid;
  String _device;
  String _token;
  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _sub;
  Timer? _heartbeat;
  Timer? _reconnect;
  int _attempt = 0;
  int _generation = 0;
  bool _disposed = false;
  bool _registered = false;
  String _clientId = '';
  WsState _state = WsState.offline;

  final List<Map<String, dynamic>> _pending = <Map<String, dynamic>>[];

  void Function(WsState state)? onStateChanged;
  void Function(String type, Map<String, dynamic> data)? onStageAction;
  void Function(String text)? onChatText;
  void Function(String delta)? onStreamDelta;
  void Function(String text)? onAsrText;
  void Function(String message)? onError;
  void Function(String direction, String type, int bytes)? onFrameLog;
  void Function(bool ok, String uid, String message)? onRegisterResult;

  bool get isReady => _state == WsState.connected && _clientId.isNotEmpty;
  bool get isRegistered => _registered;
  WsState get state => _state;
  String get clientId => _clientId;
  String get url => _url;
  String get uid => _uid;

  void setIdentity(String uid, {String device = DeviceIdentity.mobile, String token = ''}) {
    _uid = DeviceIdentity.normalize(uid);
    _device = device;
    _token = token;
  }

  void connect() {
    if (_disposed) return;
    _cancelTimers();
    final int gen = ++_generation;
    _closeChannel();
    if (_url.isEmpty) {
      // 扫码跳过：离线单机演出，模型可用，不发起任何连接/重连空转。
      _clientId = '';
      _registered = false;
      _setState(WsState.offline);
      return;
    }
    _setState(_attempt == 0 ? WsState.connecting : WsState.reconnecting);
    try {
      final WebSocketChannel ch = WebSocketChannel.connect(Uri.parse(_url));
      _channel = ch;
      _sub = ch.stream.listen(
        (dynamic raw) => _handleMessage(raw, gen),
        onDone: () => _onClosed(gen),
        onError: (Object _) => _onClosed(gen),
        cancelOnError: true,
      );
    } catch (_) {
      _scheduleReconnect();
    }
  }

  /// 设定页「重连」：换地址 / 从离线恢复都走这里。
  /// force=true 时即使地址没变也重建连接（用户主动点「重连」的语义）。
  void updateUrl(String newUrl, {bool force = false}) {
    final String normalized = newUrl.trim();
    if (normalized == _url && !force && _state != WsState.offline) return;
    _url = normalized;
    reconnect();
  }

  void reconnect() {
    if (_disposed) return;
    _attempt = 0;
    _clientId = '';
    _registered = false;
    WsFrame.nextEpoch();
    _pending.clear();
    connect();
  }

  void _onClosed(int gen) {
    if (gen != _generation || _disposed) return;
    _scheduleReconnect();
  }

  void _handleMessage(dynamic raw, int gen) {
    if (raw is! String || gen != _generation || _disposed) return;
    final Map<String, dynamic> msg = WsFrame.decode(raw);
    final String type = (msg['type'] ?? '').toString();
    final dynamic rawData = msg['data'];
    final Map<String, dynamic> data = rawData is Map<String, dynamic>
        ? rawData
        : (rawData is Map ? Map<String, dynamic>.from(rawData) : <String, dynamic>{});
    _log('in', type, raw.length);

    // U07：丢弃自己被回灌的帧。服务端出站帧的 from_id 在顶层，设备帧也可能
    // 把 from_id / client_id 放进 data；CONNECT / REGISTER / HEARTBEAT / RESULT 例外。
    final String fromId = (msg['from_id'] ?? data['from_id'] ?? '').toString();
    final String originClient = (data['client_id'] ?? '').toString();
    final bool controlFrame = type == WsEvent.connect ||
        type == WsEvent.register ||
        type == WsEvent.heartbeat ||
        type == WsEvent.result;
    if (_clientId.isNotEmpty &&
        ((fromId.isNotEmpty && fromId == _clientId) ||
            (!controlFrame && originClient.isNotEmpty && originClient == _clientId))) {
      return;
    }

    switch (type) {
      case WsEvent.connect:
        _clientId = (data['client_id'] ?? '').toString();
        _attempt = 0;
        _registered = false;
        _setState(WsState.connected);
        // 首帧 REGISTER（控制帧，不带 client_id），其后才放行业务帧。
        sendRegister();
        _flushPending();
        sendHello();
        _startHeartbeat();
        break;
      case WsEvent.register:
        _registered = msg['ok'] != false;
        onRegisterResult?.call(
          _registered,
          (data['uid'] ?? _uid).toString(),
          (msg['message'] ?? '').toString(),
        );
        break;
      case WsEvent.heartbeat:
        break;
      case WsEvent.devicePlayAnimation:
      case WsEvent.deviceStageEvent:
        onStageAction?.call((data['action'] ?? '').toString(), data);
        break;
      case WsEvent.deviceModelSet:
        onStageAction?.call('model_set', data);
        break;
      case WsEvent.deviceTextInput:
      case WsEvent.deviceAsrText:
      case WsEvent.chat:
        final String text =
            WsFrame.textFrom(rawData, maxLength: AppConfig.maxTextLength);
        if (text.isNotEmpty) onChatText?.call(text);
        break;
      case WsEvent.pipelineTextDelta:
        // 流式增量：data 是字符串片段，只追加。
        final String delta =
            WsFrame.textFrom(rawData, maxLength: AppConfig.maxTextLength);
        if (delta.isNotEmpty) onStreamDelta?.call(delta);
        break;
      case WsEvent.pipelineFinalText:
        // 终态：data 是完整台词（chat.py 的 LLM_FINAL_TEXT），必须覆盖而非追加，
        // 否则每轮回复都会接在上一轮后面。
        final String finalText =
            WsFrame.textFrom(rawData, maxLength: AppConfig.maxTextLength);
        if (finalText.isNotEmpty) onChatText?.call(finalText);
        break;
      case WsEvent.recordChunk:
      case WsEvent.recordAsrResult:
      case WsEvent.pipelineAsrText:
        // record.audio_chunk 既可能是回执 Map（无 text），也可能是 ASR 中间文本；
        // record.asr_result / pipeline.asr_text 的 data 是 {"text": "..."}。
        // textFrom 会丢掉音频回执 / base64，避免把音频当台词自动发出去。
        final String asr =
            WsFrame.textFrom(rawData, maxLength: AppConfig.maxTextLength);
        if (asr.isNotEmpty) onAsrText?.call(asr);
        break;
      case WsEvent.result:
        if (msg['ok'] == false) onError?.call((msg['message'] ?? '').toString());
        break;
      case 'error':
      case WsEvent.error:
        onError?.call((msg['message'] ?? '未知错误').toString());
        break;
      default:
        break;
    }
  }

  void sendRegister() {
    if (_disposed || _clientId.isEmpty) return;
    _sendEnvelope(WsFrame.register(
      uid: DeviceIdentity.normalize(_uid),
      device: _device,
      token: _token,
    ));
  }

  void _send(String type, Map<String, dynamic> data, String streamPrefix) {
    final int seq = WsFrame.nextSeq();
    final String rid = 'm-$streamPrefix-${WsFrame.epoch}-$seq';
    final Map<String, dynamic> env = WsFrame.envelope(
      type: type,
      data: data,
      clientId: _clientId,
      requestId: rid,
      streamId: '$streamPrefix-1',
    );
    if (!isReady) {
      // U02：拿到 client_id 之前业务帧进有界队列，超限丢最旧。
      if (_pending.length >= AppConfig.maxPendingFrames) _pending.removeAt(0);
      _pending.add(env);
      return;
    }
    _sendEnvelope(env);
  }

  void _sendEnvelope(Map<String, dynamic> env) {
    final WebSocketChannel? ch = _channel;
    if (ch == null || _disposed) return;
    try {
      final String raw = WsFrame.encode(env);
      ch.sink.add(raw);
      _log('out', (env['type'] ?? '').toString(), raw.length);
    } catch (_) {
      _scheduleReconnect();
    }
  }

  void _flushPending() {
    final List<Map<String, dynamic>> copy = List<Map<String, dynamic>>.from(_pending);
    _pending.clear();
    for (final Map<String, dynamic> env in copy) {
      _sendEnvelope(<String, dynamic>{
        ...env,
        'data': <String, dynamic>{
          ...(env['data'] as Map<String, dynamic>),
          'client_id': _clientId,
        },
      });
    }
  }

  void sendHello() =>
      _send(WsEvent.deviceHello, <String, dynamic>{'role': DeviceIdentity.mobile}, 'hello');

  void sendPose(double a, double b, double g, int t) {
    if (!isReady) return;
    _send(WsEvent.devicePose, <String, dynamic>{
      'alpha': a,
      'beta': b,
      'gamma': g,
      'seq': WsFrame.nextSeq(),
      'epoch': WsFrame.epoch,
      't': t,
    }, 'pose');
  }

  void sendStage(String action, {Map<String, dynamic>? params, int? seq}) {
    _send(WsEvent.deviceStageEvent, <String, dynamic>{
      'action': action,
      'seq': seq ?? WsFrame.nextSeq(),
      'epoch': WsFrame.epoch,
      't': DateTime.now().millisecondsSinceEpoch,
      'params': params ?? <String, dynamic>{},
    }, 'stage');
  }

  /// 打字输入实时送电脑端（device.text_input → desktop）。
  void sendTextInput(String text, {String source = 'text'}) {
    final String t = text.trim();
    if (t.isEmpty || t.length > AppConfig.maxTextLength) return;
    _send(WsEvent.deviceTextInput, <String, dynamic>{
      'text': t,
      'source': source,
      'from': DeviceIdentity.mobile,
      'seq': WsFrame.nextSeq(),
      't': DateTime.now().millisecondsSinceEpoch,
    }, 'text');
  }

  /// ASR 中间/最终文本送电脑端（device.asr_text → desktop）。
  void sendAsrText(String text) {
    final String t = text.trim();
    if (t.isEmpty || t.length > AppConfig.maxTextLength) return;
    _send(WsEvent.deviceAsrText, <String, dynamic>{
      'text': t,
      'source': 'asr',
      'from': DeviceIdentity.mobile,
      'seq': WsFrame.nextSeq(),
      't': DateTime.now().millisecondsSinceEpoch,
    }, 'asr');
  }

  /// 对话流水线：服务端会把输入与最终台词按 uid 同步给 desktop。
  void sendChat(String text, {String source = 'text'}) {
    final String t = text.trim();
    if (t.isEmpty || t.length > AppConfig.maxTextLength) return;
    _send(WsEvent.chat, <String, dynamic>{
      'message': t,
      'text': t,
      'source': source,
      'session_id': '默认会话',
      'from': DeviceIdentity.mobile,
    }, 'chat');
  }

  void sendRecordStart() =>
      _send(WsEvent.recordStart, <String, dynamic>{'from': DeviceIdentity.mobile}, 'asr');

  void sendAudioChunk(String base64, bool isFinal) {
    if (!isReady) return;
    _send(WsEvent.recordChunk, <String, dynamic>{
      'audio': base64,
      'is_final': isFinal,
      'format': 'wav',
      'from': DeviceIdentity.mobile,
    }, 'asr');
  }

  void sendRecordStop() =>
      _send(WsEvent.recordStop, <String, dynamic>{'from': DeviceIdentity.mobile}, 'asr');

  void sendModelSet(String modelId, String modelPath) {
    _send(WsEvent.deviceModelSet, <String, dynamic>{
      'model_id': modelId,
      'model_path': modelPath,
      'seq': WsFrame.nextSeq(),
      't': DateTime.now().millisecondsSinceEpoch,
    }, 'model');
  }

  /// 重连后只同步最后一个舞台快照，不补发历史演出（F07 / U49）。
  /// action=snapshot 在服务端 route 到 self，不会跨端广播。
  void sendSnapshot(String stateName, int seq) {
    _send(WsEvent.deviceStageEvent, <String, dynamic>{
      'action': 'snapshot',
      'seq': seq,
      'epoch': WsFrame.epoch,
      't': DateTime.now().millisecondsSinceEpoch,
      'params': <String, dynamic>{'snapshot': stateName},
    }, 'stage');
  }

  void _startHeartbeat() {
    _heartbeat?.cancel();
    _heartbeat = Timer.periodic(AppConfig.heartbeatInterval, (Timer _) {
      final WebSocketChannel? ch = _channel;
      if (ch == null || !isReady) return;
      try {
        final Map<String, dynamic> env = WsFrame.envelope(
          type: WsEvent.heartbeat,
          data: <String, dynamic>{},
          clientId: _clientId,
          requestId: 'm-hb-${WsFrame.nextSeq()}',
          streamId: 'heartbeat',
        );
        final String raw = WsFrame.encode(env);
        ch.sink.add(raw);
        _log('out', WsEvent.heartbeat, raw.length);
      } catch (_) {
        _scheduleReconnect();
      }
    });
  }

  void _scheduleReconnect() {
    if (_disposed) return;
    _closeChannel();
    _clientId = '';
    _registered = false;
    _cancelTimers();
    if (_url.isEmpty || !AppConfig.autoReconnect) {
      _setState(WsState.offline);
      return;
    }
    _attempt++;
    if (_attempt > AppConfig.maxReconnectAttempts) {
      _setState(WsState.offline);
      return;
    }
    _setState(WsState.reconnecting);
    final int seconds = math.min(
      1 << math.min(_attempt - 1, 4),
      AppConfig.reconnectMax.inSeconds,
    );
    _reconnect = Timer(Duration(seconds: seconds), () {
      WsFrame.nextEpoch();
      connect();
    });
  }

  void _closeChannel() {
    final StreamSubscription<dynamic>? sub = _sub;
    _sub = null;
    try {
      sub?.cancel();
    } catch (_) {}
    final WebSocketChannel? ch = _channel;
    _channel = null;
    if (ch != null) {
      try {
        ch.sink.close(ws_status.normalClosure);
      } catch (_) {}
    }
  }

  void _cancelTimers() {
    _heartbeat?.cancel();
    _heartbeat = null;
    _reconnect?.cancel();
    _reconnect = null;
  }

  void _setState(WsState value) {
    if (_state == value) return;
    _state = value;
    onStateChanged?.call(value);
  }

  void _log(String direction, String type, int bytes) {
    onFrameLog?.call(direction, type, bytes);
  }

  Future<void> dispose() async {
    _disposed = true;
    _generation++;
    _cancelTimers();
    final StreamSubscription<dynamic>? sub = _sub;
    _sub = null;
    if (sub != null) {
      try {
        await sub.cancel();
      } catch (_) {}
    }
    final WebSocketChannel? ch = _channel;
    _channel = null;
    if (ch != null) {
      try {
        await ch.sink.close(ws_status.normalClosure);
      } catch (_) {}
    }
    _pending.clear();
    // 断开所有回调引用，避免页面销毁后仍持有 State / BuildContext。
    onStateChanged = null;
    onStageAction = null;
    onChatText = null;
    onStreamDelta = null;
    onAsrText = null;
    onError = null;
    onFrameLog = null;
    onRegisterResult = null;
  }
}
