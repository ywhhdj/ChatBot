import 'package:flutter/material.dart';

import '../../app/gal_palette.dart';
import '../../core/config/app_config.dart';
import 'camera_layer.dart';

/// 背景层：相机开启后就是**纯实时相机画面**作为模型背后的背景。
///
/// 修复：
/// * 相机开启时**不再叠任何颜色蒙版**（原来压了一层 .32/.46 深蓝渐变），
///   也不再画静态夜景图 —— 用户要的就是相机本身；
/// * 相机层用 `Positioned.fill` 明确铺满 Stack，`ValueKey` 同时含档位与前后置，
///   换镜头 / 换分辨率立即重建 controller；
/// * 资源缺失时纯渐变兜底；夜景图实例静态缓存 + cacheWidth 限制解码内存，
///   并且只在相机未开启时参与绘制（省一次无用的纹理合成）。
class BackgroundLayer extends StatelessWidget {
  const BackgroundLayer({super.key});

  static final Image _night = Image.asset(
    'assets/background/night.webp',
    fit: BoxFit.cover,
    cacheWidth: 720,
    errorBuilder: (_, _, _) => const SizedBox.shrink(),
  );

  @override
  Widget build(BuildContext context) {
    final bool cameraOn = AppConfig.cameraEnabled;
    final GalPaletteData p = GalPalette.of(context);
    return DecoratedBox(
      decoration: BoxDecoration(gradient: p.background),
      child: Stack(
        fit: StackFit.expand,
        children: <Widget>[
          if (!cameraOn) const RepaintBoundary(child: _NightBackdrop()),
          if (cameraOn)
            Positioned.fill(
              // 档位 / 前置后置变了必须重建 CameraController（参数在 initState 里选定）。
              child: CameraLayer(
                key: ValueKey<String>(
                  '${AppConfig.quality.index}-${AppConfig.cameraFacing.index}',
                ),
              ),
            ),
          // 注意：这里故意不叠任何颜色蒙版。对话框 / 状态栏自身带半透明底色，
          // 足以保证文字可读，不需要再给相机画面染色。
        ],
      ),
    );
  }
}

/// 静态夜景图单独成件，只为了把 static final Image 复用进 const 构造的父子树。
class _NightBackdrop extends StatelessWidget {
  const _NightBackdrop();

  @override
  Widget build(BuildContext context) => BackgroundLayer._night;
}
