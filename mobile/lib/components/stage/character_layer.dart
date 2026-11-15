import 'package:ar_live2d_agent/app/stage_session.dart';
import 'package:flutter/material.dart';
import 'package:flutter_live2d/flutter_live2d.dart';

import '../../app/stage_scope.dart';
import '../../core/stage/stage_transform.dart';
import '../../services/live2d/live2d_stage.dart';

/// 立绘层：Transform / ClipRect / Opacity 全在组件层，core 只给数值。
class CharacterLayer extends StatelessWidget {
  const CharacterLayer({super.key, required this.transform});

  final StageTransform transform;

  @override
  Widget build(BuildContext context) {
    final StageSession session = StageScope.of(context);
    final Live2DStage stage = session.live2d;
    final Live2DViewController? controller = stage.controller;

    Widget body;
    if (stage.ready && controller != null) {
      body = IgnorePointer(child: Live2DView(controller: controller));
    } else {
      // F03：无模型时的占位立绘（纯渐变 + 名牌），不下载任何资源。
      body = DecoratedBox(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.bottomCenter,
            end: Alignment.topCenter,
            colors: <Color>[
              const Color(0xFF3A2350).withOpacity(.85),
              const Color(0xFF140E1A).withOpacity(.1),
            ],
          ),
        ),
        child: Center(
          child: Text(session.dialogText.value.isEmpty ? '？' : '她',
              style: const TextStyle(color: Colors.white70, fontSize: 48)),
        ),
      );
    }

    Widget layer = Transform.translate(
      offset: Offset(transform.dx, 0),
      child: Transform.rotate(
        angle: transform.rotationRad + transform.turnDeg * 0.003,
        child: Transform.scale(scale: transform.scale, child: body),
      ),
    );
    if (transform.peekClip) {
      // U12：overshoot 只作用于水平位移，垂直/缩放不过冲。
      layer = ClipRect(
        clipper: _PeekClipper(transform.peekFraction),
        child: layer,
      );
    }
    return RepaintBoundary(
      child: Opacity(opacity: transform.opacity, child: layer),
    );
  }
}

class _PeekClipper extends CustomClipper<Rect> {
  const _PeekClipper(this.fraction);
  final double fraction;

  @override
  Rect getClip(Size size) => Rect.fromLTWH(
        size.width * (1 - fraction), 0, size.width * fraction, size.height);

  @override
  bool shouldReclip(_PeekClipper old) => old.fraction != fraction;
}
