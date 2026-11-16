import 'package:ar_live2d_agent/core/config/load_result.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Future<bool> 返回 false 就是失败，不抛异常也必须降级', () {
    final LoadVerdict v = LoadResultInterpreter.interpret(
      futureValue: false,
      stateIsLoaded: null,
      stateError: '',
    );
    expect(v.ok, isFalse);
    expect(v.error, 'LOAD_FAILED');
  });

  test('false 时优先显示原生侧的 lastError', () {
    final LoadVerdict v = LoadResultInterpreter.interpret(
      futureValue: false,
      stateIsLoaded: false,
      stateError: 'LOAD_FAILED · Native loadModel returned false',
    );
    expect(v.ok, isFalse);
    expect(v.error, contains('LOAD_FAILED'));
  });

  test('返回 true 但 lastError 有值 → 仍然判失败（异步失败不能被吞）', () {
    final LoadVerdict v = LoadResultInterpreter.interpret(
      futureValue: true,
      stateIsLoaded: true,
      stateError: 'TEXTURE_FAILED',
    );
    expect(v.ok, isFalse);
    expect(v.error, 'TEXTURE_FAILED');
  });

  test('返回 true 但 isLoaded=false → 判失败', () {
    final LoadVerdict v = LoadResultInterpreter.interpret(
      futureValue: true,
      stateIsLoaded: false,
      stateError: '',
    );
    expect(v.ok, isFalse);
    expect(v.error, contains('isLoaded'));
  });

  test('true + isLoaded=true + 无错误 → 才是真正的就绪', () {
    final LoadVerdict v = LoadResultInterpreter.interpret(
      futureValue: true,
      stateIsLoaded: true,
      stateError: '',
    );
    expect(v.ok, isTrue);
    expect(v.error, isEmpty);
  });

  test('老版本返回 void：只能以响应式状态为准', () {
    expect(
      LoadResultInterpreter.interpret(
        futureValue: null,
        stateIsLoaded: true,
        stateError: '',
      ).ok,
      isTrue,
    );
    expect(
      LoadResultInterpreter.interpret(
        futureValue: null,
        stateIsLoaded: null,
        stateError: '',
      ).ok,
      isFalse,
    );
  });

  test('读不到任何确认信号时宁可报未确认，绝不谎报就绪', () {
    final LoadVerdict v = LoadResultInterpreter.interpret(
      futureValue: null,
      stateIsLoaded: null,
      stateError: '',
    );
    expect(v.ok, isFalse);
    expect(v.error, contains('无法确认'));
  });

  test('失败文案明确区分「文件齐全」与「模型可解析」', () {
    final String text = LoadResultInterpreter.failureText('LOAD_FAILED');
    expect(text, contains('LOAD_FAILED'));
    expect(text, contains('文件齐全不代表模型可解析'));
    expect(LoadResultInterpreter.failureText('X', threw: true),
        contains('调用异常'));
  });
}
