import 'package:flutter/material.dart';

import '../../app/gal_palette.dart';
import '../../core/config/app_config.dart';
import 'camera_layer.dart';

/// 背景层：相机开启后就是**纯实时相机画面**作为模型背后的背景。
///
/// 修复：
/// * 原来引用 `assets/background/night.webp`，但仓库里根本没有这个文件，
///   静态 Image widget 常驻内存、每次还白跑一次失败的 asset 加载；
///   现在改成纯渐变 + 柔光晕，夜色 galgame 氛围不变，零资源依赖；
/// * 相机开启时不叠任何颜色蒙版，对话框 / 状态栏自身带半透明底色；
/// * 相机层用 Positioned.fill 铺满，换档位 / 前后置靠 ValueKey 重建 controller。
class BackgroundLayer extends StatelessWidget {
  const BackgroundLayer({super.key, this.frozen = false});

  /// 后台省电 / 面板隐藏时置 true：把整棵 CameraLayer 移出渲染树，
  /// 让它的 dispose 真正释放相机控制器。
  /// 原来只停了帧泵，相机预览仍在后台采集耗电，与「几乎无帧」的承诺不符。
  final bool frozen;

  @override
  Widget build(BuildContext context) {
    final bool cameraOn = AppConfig.cameraEnabled && !frozen;
    final GalPaletteData p = GalPalette.of(context);
    return DecoratedBox(
      decoration: BoxDecoration(gradient: p.background),
      child: Stack(
        fit: StackFit.expand,
        children: <Widget>[
          if (!cameraOn) const RepaintBoundary(child: _NightBackdrop()),
          if (cameraOn)
            Positioned.fill(
              child: CameraLayer(
                key: ValueKey<String>(
                  '${AppConfig.quality.index}-${AppConfig.cameraFacing.index}',
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// 静态夜色：只用当前色系画渐变与柔光，不加载任何图片资源。
class _NightBackdrop extends StatelessWidget {
  const _NightBackdrop();

  @override
  Widget build(BuildContext context) {
    final GalPaletteData p = GalPalette.of(context);
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: <Color>[
            p.characterA.withValues(alpha: .18),
            p.bgBottom.withValues(alpha: .02),
          ],
        ),
      ),
      child: Align(
        alignment: const Alignment(0, -0.35),
        child: FractionallySizedBox(
          widthFactor: 0.9,
          heightFactor: 0.55,
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: RadialGradient(
                colors: <Color>[
                  p.accentSoft.withValues(alpha: .12),
                  Colors.transparent,
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
