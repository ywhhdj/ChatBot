import 'dart:async';
import 'dart:math' as math;

import 'package:web_socket_channel/status.dart' as ws_status;
import 'package:web_socket_channel/web_socket_channel.dart';

import '../config/app_config.dart';
import 'ws_frame.dart';

enum WsState { offline, connecting, connected, reconnecting }

/// 唯一通信出口。所有业务帧统一封成 §2.2 信封；断线不空转、不补姿态流（U04/U05/U08）。
/// 调试探针以回调注入（app/ 层在 if (kStageDebug) 分支里接 DebugBus），core 不 import debug/*。
class WsService {
  WsService({required String url}) : _url = url;

  String _url;
  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _sub;
  Timer? _heartbeat;
  Timer? _reconnect;
  int _attempt = 0;
  bool _disposed = false;
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

  bool get isReady => _state == WsState.connected && _clientId.isNotEmpty;
  WsState get state => _state;
  String get clientId => _clientId;

  void connect() {
    if (_disposed) return;
    _cancelTimers();
    final WebSocketChannel? old = _channel;
    _channel = null;
    _sub?.cancel();
    _sub = null;
    try {
      old?.sink.close(ws_status.normalClosure);
    } catch (_) {}

    _setState(_attempt == 0 ? WsState.connecting : WsState.reconnecting);
    try {
      final WebSocketChannel ch = WebSocketChannel.connect(Uri.parse(_url));
      _channel = ch;
      _sub = ch.stream.listen(
        _handleMessage,
        onDone: _scheduleReconnect,
        onError: (Object _) => _scheduleReconnect(),
        cancelOnError: true,
      );
    } catch (_) {
      _scheduleReconnect();
    }
  }

  void updateUrl(String newUrl) {
    if (newUrl == _url) return;
    _url = newUrl;
    _attempt = 0;
    _clientId = '';
    WsFrame.nextEpoch();
    _pending.clear();
    connect();
  }

  void _handleMessage(dynamic raw) {
    if (raw is! String) return;
    final Map<String, dynamic> msg = WsFrame.decode(raw);
    final String type = (msg['type'] ?? '').toString();
    final dynamic rawData = msg['data'];
    final Map<String, dynamic> data = rawData is Map<String, dynamic>
        ? rawData
        : (rawData is Map ? Map<String, dynamic>.from(rawData) : <String, dynamic>{});
    _log('in', type, raw.length);

    // U07：丢弃自己发出又被回灌的帧。
    final String from = (data['from_id'] ?? '').toString();
    if (from.isNotEmpty && from == _clientId) return;

    switch (type) {
      case 'websocket.connect':
        _clientId = (data['client_id'] ?? '').toString();
        _attempt = 0;
        _setState(WsState.connected);
        _flushPending();
        sendHello();
        _startHeartbeat();
        break;
      case 'websocket.heartbeat':
        // 服务端心跳回执：以它为真值维持三态（U05）
        break;
      case 'device.play_animation':
      case 'device.stage_event':
        onStageAction?.call((data['action'] ?? '').toString(), data);
        break;
      case 'device.model_set':
        onStageAction?.call('model_set', data);
        break;
      case 'chat':
        onChatText?.call((data['message'] ?? data['text'] ?? '').toString());
        break;
      case 'pipeline.text_delta':
      case 'pipeline.final_text':
        onStreamDelta?.call(rawData == null ? '' : rawData.toString());
        break;
      case 'record.audio_chunk':
      case 'record.asr_result':
      case 'pipeline.asr_text':
        if (rawData != null) onAsrText?.call(rawData.toString());
        break;
      case 'result':
        if (msg['ok'] == false) onError?.call((msg['message'] ?? '').toString());
        break;
      case 'error':
      case 'websocket.error':
        onError?.call((msg['message'] ?? '未知错误').toString());
        break;
      default:
        break;
    }
  }

  void _send(String type, Map<String, dynamic> data, String streamPrefix) {
    final int seq = WsFrame.nextSeq();
    final String rid = 'm-$streamPrefix-${WsFrame.epoch}-$seq';
    final String sid = '$streamPrefix-1';
    final Map<String, dynamic> env = WsFrame.envelope(
      type: type, data: data, clientId: _clientId,
      requestId: rid, streamId: sid,
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
    if (ch == null) return;
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
        'data': <String, dynamic>{...(env['data'] as Map<String, dynamic>), 'client_id': _clientId},
      });
    }
  }

  void sendHello() => _send('device.hello', <String, dynamic>{'role': 'mobile'}, 'hello');

  void sendPose(double a, double b, double g, int t) {
    if (!isReady) return;
    _send('device.pose', <String, dynamic>{
      'alpha': a, 'beta': b, 'gamma': g,
      'seq': WsFrame.nextSeq(), 'epoch': WsFrame.epoch, 't': t,
    }, 'pose');
  }

  void sendStage(String action, {Map<String, dynamic>? params, int? seq}) {
    _send('device.stage_event', <String, dynamic>{
      'action': action,
      'seq': seq ?? WsFrame.nextSeq(),
      'epoch': WsFrame.epoch,
      't': DateTime.now().millisecondsSinceEpoch,
      'params': params ?? <String, dynamic>{},
    }, 'stage');
  }

  void sendChat(String text, {String source = 'text'}) {
    final String t = text.trim();
    if (t.isEmpty || t.length > AppConfig.maxTextLength) return;
    _send('chat', <String, dynamic>{
      'message': t,
      'text': t,
      'source': source,
      'session_id': '默认会话',
      'from': 'mobile',
    }, 'chat');
  }

  void sendRecordStart() => _send('record.start', <String, dynamic>{'from': 'mobile'}, 'asr');

  void sendAudioChunk(String base64, bool isFinal) {
    if (!isReady) return;
    _send('record.audio_chunk', <String, dynamic>{
      'audio': base64, 'is_final': isFinal, 'format': 'wav', 'from': 'mobile',
    }, 'asr');
  }

  void sendRecordStop() => _send('record.stop', <String, dynamic>{'from': 'mobile'}, 'asr');

  void sendModelSet(String modelId, String modelPath) {
    _send('device.model_set', <String, dynamic>{
      'model_id': modelId, 'model_path': modelPath,
      'seq': WsFrame.nextSeq(), 't': DateTime.now().millisecondsSinceEpoch,
    }, 'model');
  }

  /// 重连后只同步最后一个舞台快照，不补发历史演出（F07 / U49）。
  void sendSnapshot(String stateName, int seq) {
    _send('device.stage_event', <String, dynamic>{
      'action': 'return_idle',
      'seq': seq, 'epoch': WsFrame.epoch,
      't': DateTime.now().millisecondsSinceEpoch,
      'params': <String, dynamic>{'snapshot': stateName},
    }, 'stage');
  }

  void _startHeartbeat() {
    _heartbeat?.cancel();
    _heartbeat = Timer.periodic(AppConfig.heartbeatInterval, (Timer _) {
      final WebSocketChannel? ch = _channel;
      if (ch == null) return;
      try {
        ch.sink.add('{"type":"websocket.heartbeat"}');
        _log('out', 'websocket.heartbeat', 30);
      } catch (_) {
        _scheduleReconnect();
      }
    });
  }

  void _scheduleReconnect() {
    if (_disposed) return;
    _channel = null;
    _clientId = '';
    _cancelTimers();
    _setState(WsState.reconnecting);
    _attempt++;
    final int seconds = math.min(
      1 << math.min(_attempt - 1, 4),
      AppConfig.reconnectMax.inSeconds,
    );
    _reconnect?.cancel();
    _reconnect = Timer(Duration(seconds: seconds), () {
      _clientId = '';
      WsFrame.nextEpoch();
      connect();
    });
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
    _cancelTimers();
    await _sub?.cancel();
    _sub = null;
    try {
      await _channel?.sink.close(ws_status.normalClosure);
    } catch (_) {}
    _channel = null;
    _pending.clear();
  }
}
