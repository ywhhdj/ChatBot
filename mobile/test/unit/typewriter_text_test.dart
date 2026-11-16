import 'package:ar_live2d_agent/components/stage/typewriter_text.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('中文按字符逐个推进', () {
    expect(TypewriterTextState.nextVisible('你好', 0), 1);
    expect(TypewriterTextState.nextVisible('你好', 1), 2);
    expect(TypewriterTextState.nextVisible('你好', 2), 2);
  });

  test('emoji 代理对一次跨两格，substring 不会切出半个字符', () {
    const String text = '😀好';
    expect(text.length, 3); // high + low surrogate + '好'
    final int first = TypewriterTextState.nextVisible(text, 0);
    expect(first, 2);
    expect(text.substring(0, first), '😀');
    expect(TypewriterTextState.nextVisible(text, first), 3);
  });

  test('越界 / 空串不会抛异常', () {
    expect(TypewriterTextState.nextVisible('', 0), 0);
    expect(TypewriterTextState.nextVisible('abc', 9), 3);
    expect(TypewriterTextState.nextVisible('abc', 3), 3);
  });
}
