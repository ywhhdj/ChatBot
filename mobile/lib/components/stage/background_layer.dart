import 'package:flutter/material.dart';

import '../../core/config/app_config.dart';
import 'camera_layer.dart';

/// 背景层：仓库内资源（用户自备）缺失时纯渐变兜底，不下载素材。
class BackgroundLayer extends StatelessWidget {
  const BackgroundLayer({super.key});

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: <Color>[Color(0xFF1B1026), Color(0xFF0B0710)],
        ),
      ),
      child: Stack(
        fit: StackFit.expand,
        children: <Widget>[
          Image.asset(
            'assets/background/night.webp',
            fit: BoxFit.cover,
            errorBuilder: (_, __, ___) => const SizedBox.shrink(),
          ),
          if (AppConfig.cameraEnabled) const CameraLayer(),
        ],
      ),
    );
  }
}
