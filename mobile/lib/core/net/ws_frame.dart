import 'dart:convert';

import '../../debug/debug_flags.dart';
import 'ws_events.dart';

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

  /// REGISTER 是 CONTROL_EVENTS：**不带 data.client_id**、不占业务 inflight，
  /// 且必须是 CONNECT 之后的第一帧（docs/api.md §4.5.1）。
  static Map<String, dynamic> register({
    required String uid,
    String device = 'mobile',
    String token = '',
  }) {
    final int seq = nextSeq();
    return <String, dynamic>{
      'type': WsEvent.register,
      'data': <String, dynamic>{
        'uid': uid,
        'device': device,
        'token': token,
      },
      'request_id': 'm-register-$_epoch-$seq',
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

  /// 从 data 里安全取文本：字符串直接取，Map 取 text / message / delta。
  ///
  /// 过滤音频回执、结构化调试串与纯 base64 长串，避免把
  /// `record.audio_chunk` 的回执当成台词或聊天输入再发出去。
  /// `pipeline.final_text` 是整段台词，`pipeline.text_delta` 是片段，
  /// 两者都用这里取文本，再由 WsService 决定覆盖还是追加。
  static String textFrom(dynamic raw, {int maxLength = 2000}) {
    String text;
    if (raw is String) {
      text = raw;
    } else if (raw is Map) {
      final dynamic v = raw['text'] ?? raw['message'] ?? raw['delta'] ?? '';
      text = v is String ? v : '';
    } else {
      return '';
    }
    final String t = text.trim();
    if (t.isEmpty || t.length > maxLength) return '';
    if (t.startsWith('{') || t.startsWith('[') || t.contains('"audio"')) return '';
    // 纯 base64 长串：音频分片误入文本通道时直接丢掉。
    if (t.length >= 256 && RegExp(r'^[A-Za-z0-9+/=\s]+$').hasMatch(t)) return '';
    return t;
  }
}
