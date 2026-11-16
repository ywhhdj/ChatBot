import 'package:flutter/material.dart';
import 'package:flutter_live2d/flutter_live2d.dart';

import '../../app/gal_palette.dart';
import '../../app/routes.dart';
import '../../app/stage_scope.dart';
import '../../app/stage_session.dart';
import '../../core/stage/stage_transform.dart';
import '../../services/live2d/live2d_stage.dart';

/// 立绘层：Transform / ClipRect / Opacity 全在组件层，core 只给数值。
///
/// * Live2DView 常驻树中：只要 controller 存在就挂载（未就绪时用不透明占位盖住），
///   否则插件的 `whenAttached` 永远不会完成，模型永远加载不了（死锁）；
/// * 出屏不绘制：`culled`（opacity≈0 / scale≈0）直接返回空 widget，
///   不再把模型 Transform 到屏外继续提交 GPU（离屏绘制）；
/// * 合并矩阵：translate/rotate/scale 合成一个 Transform，少两个 RenderObject；
/// * 不滥用 Opacity：只有 0<opacity<1 的演出中间态才用（会触发 saveLayer），
///   idle 常态直接画，60fps 下省掉一整层离屏合成；
/// * 模型没加载时给出「请重试」入口，而不是只画一个「？」让人以为卡死。
class CharacterLayer extends StatelessWidget {
  const CharacterLayer({super.key, required this.transform, this.session});

  final StageTransform transform;

  /// 由 StageView 直接传入，避免每帧再查一次 InheritedWidget。
  final StageSession? session;

  @override
  Widget build(BuildContext context) {
    // 出屏 / 完全透明 / 缩到 0：整个立绘子树不进渲染树。
    if (transform.culled) return const SizedBox.shrink();

    final StageSession s = session ?? StageScope.of(context);
    final Live2DStage stage = s.live2d;
    final Live2DViewController? controller = stage.controller;
    final GalPaletteData p = GalPalette.of(context);

    // 常驻视图：即使 ready=false 也保留，让 controller 有机会 attach。
    final Widget live = controller != null
        ? IgnorePointer(
            child: Live2DView(
              // 换 controller 必须换 Element，否则插件 State 仍持有旧 controller；
              // 用门面的递增 revision 而不是 hashCode（hashCode 可能碰撞，
              // 且不同 controller 复用同一 hash 时视图不会重建）。
              key: ValueKey<int>(stage.controllerRevision),
              controller: controller,
            ),
          )
        : const SizedBox.shrink();

    // 树结构保持恒定：live 永远在 Stack 的同一个位置，就绪只是把上层占位去掉。
    // 若按 ready 切换整棵子树，Live2DView 的 Element 会被销毁重建，
    // 触发二次 attach / 闪一下黑屏。
    final Widget body = Stack(
      fit: StackFit.expand,
      children: <Widget>[
        live,
        if (!stage.ready)
          DecoratedBox(
            decoration: BoxDecoration(color: p.bgBottom, gradient: p.character),
            child: Center(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 28),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    Text(
                      '？',
                      style: TextStyle(
                        color: p.accent,
                        fontSize: 48,
                        fontWeight: FontWeight.w300,
                      ),
                    ),
                    const SizedBox(height: 12),
                    Text(
                      '…… 立绘尚未就位 ……',
                      style: TextStyle(
                        color: p.accent,
                        fontSize: 13,
                        letterSpacing: 1.2,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      stage.detailText,
                      textAlign: TextAlign.center,
                      maxLines: 4,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: p.textDim,
                        fontSize: 11,
                        height: 1.5,
                      ),
                    ),
                    const SizedBox(height: 12),
                    OutlinedButton.icon(
                      style: OutlinedButton.styleFrom(
                        foregroundColor: p.accent,
                        side: BorderSide(color: p.border),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(20),
                        ),
                        padding: const EdgeInsets.symmetric(
                          horizontal: 16,
                          vertical: 6,
                        ),
                      ),
                      onPressed: () =>
                          AppRoutes.pushOnce(context, AppRoutes.settings),
                      icon: const Icon(Icons.tune, size: 14),
                      label: const Text(
                        '到「设定 → 模型」',
                        style: TextStyle(fontSize: 11),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
      ],
    );

    // 三层嵌套 Transform 合并成一个矩阵：少两个 RenderTransform / 合成层。
    final double angle = transform.rotationRad + transform.turnDeg * 0.003;
    final Matrix4 matrix = Matrix4.identity()
      ..translate(transform.dx, 0.0)
      ..rotateZ(angle)
      ..scale(transform.scale, transform.scale, 1.0);

    Widget layer = Transform(
      transform: matrix,
      alignment: Alignment.bottomCenter,
      child: body,
    );
    if (transform.peekClip) {
      // overshoot 只作用于水平位移，垂直/缩放不过冲。
      layer = ClipRect(
        clipper: _PeekClipper(transform.peekFraction),
        child: layer,
      );
    }

    // 常态不用 Opacity，避免每帧 saveLayer 离屏合成。
    final Widget painted = transform.opacity >= 0.999
        ? layer
        : Opacity(opacity: transform.opacity, child: layer);
    return RepaintBoundary(child: painted);
  }
}

class _PeekClipper extends CustomClipper<Rect> {
  const _PeekClipper(this.fraction);
  final double fraction;

  @override
  Rect getClip(Size size) => Rect.fromLTWH(
    size.width * (1 - fraction),
    0,
    size.width * fraction,
    size.height,
  );

  @override
  bool shouldReclip(_PeekClipper old) => old.fraction != fraction;
}
