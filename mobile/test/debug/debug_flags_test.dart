import 'package:flutter_test/flutter_test.dart';
import 'package:ar_live2d_agent/debug/debug_flags.dart';
import 'package:ar_live2d_agent/debug/debug_bus.dart';

void main() {
  test('调试开关是编译期常量', () {
    expect(kStageDebug, isA<bool>());
    expect(kStageFrameMeta, isA<bool>());
    expect(kStageFrameMeta && !kStageDebug, isFalse);
  });

  test('帧缓冲有上限且不记正文（U52/U33）', () {
    final DebugBus bus = DebugBus.instance;
    bus.clear();
    for (int i = 0; i < 400; i++) {
      bus.recordFrame('out', 'device.pose', 120);
    }
    expect(bus.frames.length, lessThanOrEqualTo(200));
    expect(bus.frames.first.type, 'device.pose');
  });

  test('mock 与真实源互斥标志', () {
    final DebugBus bus = DebugBus.instance;
    bus.setMock(true);
    expect(bus.isMock, isTrue);
    bus.setMock(false);
    expect(bus.isMock, isFalse);
  });
}
