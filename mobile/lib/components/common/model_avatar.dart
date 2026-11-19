import 'dart:io';

import 'package:flutter/material.dart';

import '../../app/gal_palette.dart';
import '../../core/config/model_config.dart';
import '../../core/config/model_path.dart';

/// 模型头像：有 `avatarPath` 就用图片，没有（或图片加载失败）就用 name 占位。
///
/// * 保持蓝色 galgame 渐变底：头像没加载出来时不会露出白块；
/// * `cacheWidth` 限制解码尺寸，用户放一张 4K 头像也不会吃爆内存；
/// * Image widget 按路径做有界缓存，滑动预览卡时不会每帧新建配置对象；
/// * errorBuilder 一律回退到占位，绝不把「有路径但文件不存在」变成空白卡。
class ModelAvatar extends StatelessWidget {
  const ModelAvatar({
    super.key,
    required this.model,
    this.size,
    this.radius = 12,
    this.fontSize = 40,
  });

  final ModelConfig model;

  /// 传 null = 自适应父级约束（预览卡用 Expanded 包）。
  final double? size;
  final double radius;
  final double fontSize;

  static const int _cacheWidth = 256;
  static const int _maxCached = 32;
  static final Map<String, Image> _images = <String, Image>{};
  static final List<String> _order = <String>[];

  static Image _image(String path, double? size) {
    final Image? cached = _images[path];
    if (cached != null) {
      _order.remove(path);
      _order.add(path);
      return cached;
    }
    // 预览卡只有 112px 宽，没必要按 256 解码；头像越大才放宽上限。
    final int width = size == null
        ? _cacheWidth
        : (size * 2).clamp(96, 512).toInt();
    final Image image = ModelPath.isAssetPath(path)
        ? Image.asset(
            path,
            fit: BoxFit.cover,
            cacheWidth: width,
            gaplessPlayback: true,
            errorBuilder: (_, _, _) => const SizedBox.shrink(),
          )
        : Image.file(
            File(path),
            fit: BoxFit.cover,
            cacheWidth: width,
            gaplessPlayback: true,
            errorBuilder: (_, _, _) => const SizedBox.shrink(),
          );
    _images[path] = image;
    _order.add(path);
    // LRU：旧实现一满就 clear，横向滑预览卡会反复重建配置对象。
    while (_order.length > _maxCached) {
      _images.remove(_order.removeAt(0));
    }
    return image;
  }

  String get _initial {
    if (model.name.isEmpty) return '？';
    // 用 runes 取第一个字符，避免 emoji / 代理对名字被切成半个字符。
    return String.fromCharCode(model.name.runes.first).toUpperCase();
  }

  @override
  Widget build(BuildContext context) {
    final GalPaletteData p = GalPalette.of(context);
    final String path = model.resolvedAvatarPath;
    final Widget content = ClipRRect(
      borderRadius: BorderRadius.circular(radius),
      child: DecoratedBox(
        decoration: BoxDecoration(gradient: p.character),
        child: Stack(
          fit: StackFit.expand,
          children: <Widget>[
            Center(
              child: Text(
                _initial,
                style: TextStyle(
                  color: p.accent.withValues(alpha: .85),
                  fontSize: fontSize,
                  fontWeight: FontWeight.w300,
                ),
              ),
            ),
            if (path.isNotEmpty && !path.contains('://')) _image(path, size),
          ],
        ),
      ),
    );
    return size == null
        ? content
        : SizedBox(width: size, height: size, child: content);
  }
}
