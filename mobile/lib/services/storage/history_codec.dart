import 'dart:convert';

/// 对话历史的持久化编解码（纯函数、有界、损坏数据自动兜底）。
///
/// 只保留最后 [limit] 条，避免 SharedPreferences 里堆出无上限的字符串；
/// 解码时过滤空串与非字符串元素，旧版本 / 手改过的脏数据不会让页面崩溃。
class HistoryCodec {
  HistoryCodec._();

  static const int defaultLimit = 100;

  static String encode(List<String> items, {int limit = defaultLimit}) {
    final int n = limit < 1 ? 1 : limit;
    final List<String> slice = items.length > n
        ? items.sublist(items.length - n)
        : List<String>.from(items);
    return json.encode(slice);
  }

  static List<String> decode(String? raw, {int limit = defaultLimit}) {
    if (raw == null || raw.isEmpty) return <String>[];
    try {
      final dynamic value = json.decode(raw);
      if (value is! List) return <String>[];
      final List<String> out = <String>[];
      for (final dynamic e in value) {
        if (e is String && e.isNotEmpty) out.add(e);
      }
      final int n = limit < 1 ? 1 : limit;
      return out.length > n ? out.sublist(out.length - n) : out;
    } catch (_) {
      return <String>[];
    }
  }
}
