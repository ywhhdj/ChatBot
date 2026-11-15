import 'package:flutter_test/flutter_test.dart';
import 'package:ar_live2d_agent/core/stage/stage_machine.dart';
import 'package:ar_live2d_agent/core/config/app_config.dart';

void main() {
  test('右弹 -> 甩出 -> 侧头回来 -> 复位 全时序', () {
    final List<String> emitted = <String>[];
    final StageMachine m = StageMachine(
      onEmit: (StageIntent i) => emitted.add(i.action),
    );
    m.flingOut(velocity: 1200);
    expect(m.state, StageState.flingOut);
    m.onFlingFinished();
    expect(m.state, StageState.offscreen);
    m.peekBack();
    expect(m.state, StageState.peekBack);
    m.returnIdle();
    expect(m.state, StageState.returnIdle);
    m.onIdleFinished();
    expect(m.state, StageState.idle);
    expect(emitted, <String>['fling_out', 'peek_back', 'return_idle']);
  });

  test('冷却期内重复右弹被忽略（U10）', () {
    final StageMachine m = StageMachine();
    final DateTime now = DateTime(2026, 1, 1, 12);
    m.flingOut(now: now);
    m.onFlingFinished();
    m.flingOut(now: now.add(const Duration(seconds: 1)));
    expect(m.state, StageState.offscreen);
    m.flingOut(now: now.add(AppConfig.triggerCooldown + const Duration(seconds: 1)));
    expect(m.state, StageState.flingOut);
  });

  test('远端 seq 幂等（U11）', () {
    final StageMachine m = StageMachine();
    m.remoteAction('jump_out', 7);
    expect(m.state, StageState.jumpOutLocal);
    m.remoteAction('jump_out', 7);
    expect(m.state, StageState.jumpOutLocal);
  });

  test('变换数值随进度单调右移且不越界', () {
    final StageMachine m = StageMachine();
    m.flingOut();
    final double d0 = m.transform(0, 400).dx;
    final double d1 = m.transform(1, 400).dx;
    expect(d1, greaterThan(d0));
    expect(d1, greaterThan(400));
  });
}
