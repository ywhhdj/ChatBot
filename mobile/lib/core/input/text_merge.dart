/// 输入防抖合并 / 相邻去重的纯逻辑（不依赖 Flutter，便于单元测试）。
///
/// * 前缀关系（逐字输入、ASR 中间结果）取最长那条，避免把 "你" + "你好" 拼成两句；
/// * 无前缀关系（连续提交两句）用换行合并成一条，减少 WebSocket 往返；
/// * `dedupeAdjacent` 只去掉**相邻**重复，保留间隔出现的同一句台词。
String mergeTextInput(String buffer, String next) {
  if (buffer.isEmpty) return next;
  if (next.isEmpty) return buffer;
  if (next.startsWith(buffer) || buffer.startsWith(next)) {
    return next.length >= buffer.length ? next : buffer;
  }
  return '$buffer\n$next';
}

List<String> dedupeAdjacent(Iterable<String> items) {
  final List<String> out = <String>[];
  for (final String s in items) {
    if (out.isNotEmpty && out.last == s) continue;
    out.add(s);
  }
  return out;
}

/// 检测一条新文本是否与「上一条已发送 / 历史最后一条」相邻重复。
bool isAdjacentDuplicate(String text, String lastHistory, String lastSent) {
  if (text.isEmpty) return false;
  return text == lastHistory || text == lastSent;
}
