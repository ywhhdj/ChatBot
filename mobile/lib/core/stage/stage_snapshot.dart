import 'stage_transform.dart';

/// 生命周期恢复用：不从头重播演出，按剩余时间续上
class StageSnapshot {
  const StageSnapshot({
    required this.stateName,
    required this.seq,
    required this.progress,
    required this.remainingPeekMs,
  });

  final String stateName;
  final int seq;
  final double progress;
  final int remainingPeekMs;

  StageTransform get transform => StageTransform.idle;
}
