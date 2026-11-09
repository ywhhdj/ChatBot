import 'dart:async';
import 'dart:convert';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:web_socket_channel/status.dart' as ws_status;

/// 与 PC 端通信：发送 pose / trigger 消息，接收 play_animation 指令。
class WsService {
  WsService({required String url, this.onRemoteEvent}) : _url = url;

  /// 运行时可切换 URL（扫码后调用）
  void updateUrl(String newUrl) {
    if (_url == newUrl) return;
    _url = newUrl;
    _channel = null;
    _sub?.cancel();
    _sub = null;
    _reconnectTimer?.cancel();
    connect();
  }

  final void Function(String event)? onRemoteEvent;

  WebSocketChannel? _channel;
  StreamSubscription? _sub;
  Timer? _reconnectTimer;
  int _seq = 0;
  bool _disposed = false;

  WsService({required this.url, this.onRemoteEvent});

  bool get isConnected => _channel != null;

  void connect() {
    if (_disposed) return;
    try {
      _channel = WebSocketChannel.connect(Uri.parse(url));
      _sub = _channel!.stream.listen(
        _handleMessage,
        onDone: _scheduleReconnect,
        onError: (_) => _scheduleReconnect(),
        cancelOnError: true,
      );
    } catch (_) {
      _scheduleReconnect();
    }
  }

  void sendPose(double alpha, double beta, double gamma, int t) {
    _sendRaw({
      'type': 'pose',
      'alpha': alpha,
      'beta': beta,
      'gamma': gamma,
      't': t,
    });
  }

  void sendTrigger(String event, {int? timestampMs}) {
    _sendRaw({
      'type': 'trigger',
      'event': event,
      'seq': ++_seq,
      't': timestampMs ?? DateTime.now().millisecondsSinceEpoch,
    });
  }

  void _sendRaw(Map<String, dynamic> msg) {
    final ch = _channel;
    if (ch == null) return;
    try {
      ch.sink.add(jsonEncode(msg));
    } catch (_) {
      _scheduleReconnect();
    }
  }

  void _handleMessage(dynamic raw) {
    try {
      final msg = jsonDecode(raw as String) as Map<String, dynamic>;
      if (msg['type'] == 'play_animation') {
        onRemoteEvent?.call(msg['event'] as String? ?? '');
      }
    } catch (_) {}
  }

  void _scheduleReconnect() {
    _channel = null;
    _sub?.cancel();
    _sub = null;
    if (_disposed) return;
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(const Duration(seconds: 2), connect);
  }

  Future<void> dispose() async {
    _disposed = true;
    _reconnectTimer?.cancel();
    await _sub?.cancel();
    await _channel?.sink.close(ws_status.normalClosure);
    _channel = null;
  }
}