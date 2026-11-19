import 'dart:collection';

import '../config/app_config.dart';
import '../config/stage_config.dart';
import 'stage_transform.dart';

enum StageState { idle, turn, flingOut, offscreen, peekBack, returnIdle, jumpOutLocal }

class StageIntent {
  const StageIntent(this.action, {this.params = const <String, dynamic>{}, this.seq = 0});
  final String action;
  final Map<String, dynamic> params;
  final int seq;
}

/// 纯 Dart 状态机：唯一仲裁点，本地手势与远端指令都走 transition（U10/U11）。
/// 不持有 Timer / BuildContext / AnimationController；Ticker 在 components/stage/stage_view.dart。
/// 去重 key 带 epoch 与来源端，避免两台设备恰好用同一个 seq 时误丢演出。
class StageMachine {
  StageMachine({this.onEmit});

  final void Function(StageIntent intent)? onEmit;

  StageState _state = StageState.idle;
  int _seq = 0;
  int _generation = 0;
  DateTime _lastTrigger = DateTime.fromMillisecondsSinceEpoch(0);
  final Queue<String> _seenSeq = Queue<String>();

  StageState get state => _state;
  int get generation => _generation;
  int get seq => _seq;
  int get remainingPeekMs => AppConfig.peekDelay.inMilliseconds;

  bool _canTrigger(DateTime now) {
    if (now.difference(_lastTrigger) < AppConfig.triggerCooldown) return false;
    _lastTrigger = now;
    return true;
  }

  void _set(StageState next) {
    if (_state == next) return;
    _state = next;
    _generation++;
  }

  void _emit(String action, [Map<String, dynamic>? params]) {
    _seq++;
    onEmit?.call(StageIntent(action, params: params ?? <String, dynamic>{}, seq: _seq));
  }

  /// 手指向右弹（S4.1）：冷却 + 状态锁，可打断 peek/return。
  void flingOut({double velocity = 0, DateTime? now}) {
    final DateTime t = now ?? DateTime.now();
    if (!_canTrigger(t)) return;
    if (_state == StageState.flingOut) return;
    _set(StageState.flingOut);
    _emit('fling_out', <String, dynamic>{
      'direction': 'right', 'velocity': velocity,
    });
  }

  void onFlingFinished() => _set(StageState.offscreen);

  /// 等一会儿侧头回来，只由唯一 Timer 触发一次。
  void peekBack() {
    if (_state != StageState.offscreen) return;
    _set(StageState.peekBack);
    _emit('peek_back');
  }

  /// 对端（desktop）发来的侧头指令：只切本地状态、不 emit，
  /// 否则会再转发回 desktop 形成来回回声。
  void remotePeekBack() {
    if (_state != StageState.offscreen) return;
    _set(StageState.peekBack);
  }

  /// 置顶浮窗开启：直接进入「右侧探头」并保持（不 emit、不要求先出屏）。
  /// StageView 在浮窗开启期间不启动 holdTimer，所以状态会停在 peekBack。
  void enterOverlayPeek() {
    _set(StageState.peekBack);
  }

  /// 关闭浮窗：从探头回场，并通知电脑端归位。
  void exitOverlayPeek() {
    if (_state != StageState.peekBack) return;
    _set(StageState.returnIdle);
    _emit('return_idle');
  }

  void returnIdle() {
    if (_state != StageState.peekBack && _state != StageState.jumpOutLocal) return;
    _set(StageState.returnIdle);
    _emit('return_idle');
  }

  void onIdleFinished() => _set(StageState.idle);

  void turn(double deg) {
    if (_state != StageState.idle) return;
    _set(StageState.turn);
    _emit(deg >= 0 ? 'turn_right' : 'turn_left', <String, dynamic>{'deg': deg});
    _set(StageState.idle);
  }

  /// 远端事件也走同一仲裁 + 幂等（U11/U59）。
  void remoteAction(
    String action,
    int remoteSeq, {
    int epoch = 0,
    String fromId = '',
  }) {
    final String key = '$epoch|$fromId|$remoteSeq';
    if (_seenSeq.contains(key)) return;
    _seenSeq.addLast(key);
    if (_seenSeq.length > AppConfig.maxStageSeqHistory) _seenSeq.removeFirst();
    switch (action) {
      case 'jump_out':
        if (_state == StageState.idle) {
          _set(StageState.jumpOutLocal);
          _emit('jump_out_ack');
        }
        break;
      case 'return_idle':
        if (_state == StageState.jumpOutLocal) returnIdle();
        break;
      case 'peek_back':
        // 电脑端主动探头：本地已被甩出屏幕时跟着侧头回来。
        remotePeekBack();
        break;
      default:
        break;
    }
  }

  /// 按进度输出变换数值；width 由 LayoutBuilder 实时提供（U14，绝不缓存屏宽）。
  StageTransform transform(double p, double width, {double turnDeg = 0}) {
    final double t = p < 0 ? 0 : (p > 1 ? 1 : p);
    final double outX = width * StageConfig.screenWidthFactor;
    final double rotate =
        StageConfig.flingRotationDeg * 3.141592653589793 / 180.0;
    switch (_state) {
      case StageState.flingOut:
        final double e = StageCurves.easeOutQuart(t);
        return StageTransform(
          dx: outX * e,
          rotationRad: rotate * e,
          scale: StageTransform.lerpDouble(1, StageConfig.flingScale, e),
          opacity: StageTransform.lerpDouble(1, 0.85, e),
          turnDeg: turnDeg,
        );
      case StageState.offscreen:
        return StageTransform(dx: outX, opacity: 0, turnDeg: turnDeg);
      case StageState.peekBack:
        final double e = StageCurves.easeOutBack(t);
        final double peekX = width * (1 - StageConfig.peekVisibleFraction);
        return StageTransform(
          dx: StageTransform.lerpDouble(outX, peekX, e) -
              StageConfig.peekOvershoot * (1 - t),
          opacity: StageTransform.lerpDouble(0, 1, t),
          peekClip: true,
          peekFraction: StageConfig.peekVisibleFraction,
          turnDeg: turnDeg,
        );
      case StageState.returnIdle:
        final double e = StageCurves.easeInOutCubic(t);
        final double peekX = width * (1 - StageConfig.peekVisibleFraction);
        return StageTransform(
          dx: peekX * (1 - e),
          opacity: 1,
          peekClip: t < 0.5,
          peekFraction: t < 0.5 ? StageConfig.peekVisibleFraction : 1,
          turnDeg: turnDeg,
        );
      case StageState.jumpOutLocal:
        final double e = StageCurves.easeOutQuart(t);
        return StageTransform(
          dx: -width * 0.35 * e,
          rotationRad: -rotate * 0.4 * e,
          opacity: StageTransform.lerpDouble(1, 0.9, e),
          turnDeg: turnDeg,
        );
      case StageState.turn:
      case StageState.idle:
        return StageTransform(turnDeg: turnDeg);
    }
  }

  String get snapshotName => _state.name;
}
