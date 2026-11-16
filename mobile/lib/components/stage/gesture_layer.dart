import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/config/app_config.dart';

/// 手势识别：只产出事件，不碰状态机 / 网络（S4.1 / U16-U19）。
class GestureLayer extends StatelessWidget {
  const GestureLayer({
    super.key,
    required this.child,
    required this.onFlingRight,
    required this.onTurn,
    required this.onTapRecall,
  });

  final Widget child;
  final void Function(double velocity) onFlingRight;
  final void Function(double deg) onTurn;
  final VoidCallback onTapRecall;

  @override
  Widget build(BuildContext context) {
    double startY = 0;
    double dx = 0;
    double dy = 0;
    int startMs = 0;

    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints c) {
        return GestureDetector(
          behavior: HitTestBehavior.translucent,
          onHorizontalDragStart: (DragStartDetails d) {
            startY = d.globalPosition.dy;
            dx = 0;
            dy = 0;
            startMs = DateTime.now().millisecondsSinceEpoch;
          },
          onHorizontalDragUpdate: (DragUpdateDetails d) {
            dx += d.delta.dx;
            dy += d.delta.dy;
          },
          onHorizontalDragEnd: (DragEndDetails d) {
            // U17：底部输入区不抢手势。
            if (startY > c.maxHeight * 0.75) return;
            final double v = d.primaryVelocity ??
                d.velocity.pixelsPerSecond.dx;
            final int elapsed = DateTime.now().millisecondsSinceEpoch - startMs;
            final bool dominant = dx.abs() > dy.abs() * AppConfig.swipeDominance;
            if (v > AppConfig.swipeRightVelocity &&
                dx.abs() > AppConfig.swipeMinDistance &&
                elapsed < AppConfig.swipeMaxDurationMs &&
                dominant) {
              try {
                HapticFeedback.lightImpact();
              } catch (_) {}
              onFlingRight(v);
            }
          },
          onDoubleTapDown: (TapDownDetails d) {
            final double step = AppConfig.turnStepDeg;
            onTurn(d.globalPosition.dx < c.maxWidth / 2 ? -step : step);
          },
          onTap: onTapRecall,
          child: child,
        );
      },
    );
  }
}
