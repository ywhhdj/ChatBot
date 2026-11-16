import 'package:ar_live2d_agent/services/storage/history_codec.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('编解码保序、保留空字符串以外的台词', () {
    final String raw = HistoryCodec.encode(<String>['今天也来陪我吗？', '嗯…']);
    expect(HistoryCodec.decode(raw), <String>['今天也来陪我吗？', '嗯…']);
  });

  test('超过上限只保留最后 N 条', () {
    final List<String> items =
        List<String>.generate(150, (int i) => '第 $i 句');
    final String raw = HistoryCodec.encode(items, limit: 100);
    final List<String> decoded = HistoryCodec.decode(raw, limit: 100);
    expect(decoded.length, 100);
    expect(decoded.first, '第 50 句');
    expect(decoded.last, '第 149 句');
  });

  test('编码时裁剪、解码时再裁剪，双向有界', () {
    final List<String> decoded = HistoryCodec.decode(
      HistoryCodec.encode(
        List<String>.generate(20, (int i) => '$i'),
        limit: 5,
      ),
      limit: 3,
    );
    expect(decoded, <String>['17', '18', '19']);
  });

  test('null / 空串 / 坏 JSON / 非字符串元素都安全兜底', () {
    expect(HistoryCodec.decode(null), isEmpty);
    expect(HistoryCodec.decode(''), isEmpty);
    expect(HistoryCodec.decode('{not json'), isEmpty);
    expect(HistoryCodec.decode('"a string"'), isEmpty);
    expect(HistoryCodec.decode('[1, null, "ok", {"a":1}]'), <String>['ok']);
  });

  test('limit 非法值被夹到至少 1', () {
    expect(HistoryCodec.decode('["a","b","c"]', limit: 0).length, 1);
  });
}
