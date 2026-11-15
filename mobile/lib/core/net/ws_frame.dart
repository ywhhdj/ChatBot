import 'dart:convert';

import '../../debug/debug_flags.dart';

/// 帧编解码（core/，零 Widget / 零平台副作用）。
/// 信封与 docs/contracts/device_events.md 逐字一致；release 下不拼接任何调试字段（U55）。
class WsFrame {
  WsFrame._();

  static int _epoch = 0;
  static int _seq = 0;

  static int get epoch => _epoch;
  static int nextSeq() => ++_seq;

  /// 每次重连递增 epoch，避免 seq 归零后被后端去重窗口误判（U03）。
  static void nextEpoch() {
    _epoch++;
    _seq = 0;
  }

  static Map<String, dynamic> envelope({
    required String type,
    required Map<String, dynamic> data,
    required String clientId,
    required String requestId,
    required String streamId,
  }) {
    final Map<String, dynamic> payload = <String, dynamic>{
      ...data,
      'client_id': clientId,
    };
    if (kStageFrameMeta) {
      payload['debug'] = <String, dynamic>{
        'epoch': _epoch,
        'build_ms': DateTime.now().millisecondsSinceEpoch,
      };
    }
    return <String, dynamic>{
      'type': type,
      'data': payload,
      'request_id': requestId,
      'stream_id': streamId,
      'timestamp': DateTime.now().millisecondsSinceEpoch,
    };
  }

  static String encode(Map<String, dynamic> envelope) => jsonEncode(envelope);

  static Map<String, dynamic> decode(String raw) {
    final dynamic value = jsonDecode(raw);
    if (value is Map<String, dynamic>) return value;
    if (value is Map) return Map<String, dynamic>.from(value);
    return <String, dynamic>{};
  }
}
