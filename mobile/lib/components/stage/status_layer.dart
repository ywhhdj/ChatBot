import 'package:flutter/material.dart';

import '../../app/gal_palette.dart';
import '../../app/routes.dart';
import '../../app/stage_scope.dart';
import '../../app/stage_session.dart';
import '../../core/config/app_config.dart';
import '../common/status_chip.dart';

/// 三态连接状态 + 实时帧率 / 省电 / 相机 / 模型 / 档位 + 设定与历史入口。
/// 设定和历史现在都是**全屏新页面**，不再用 bottom sheet / dialog。
class StatusLayer extends StatelessWidget {
  const StatusLayer({super.key});

  @override
  Widget build(BuildContext context) {
    final StageSession session = StageScope.of(context);
    // setPowerSave / startOverlay / applyParams 都会 notifyListeners，
    // 包一层 AnimatedBuilder 让省电、浮窗、帧率开关等状态切换即时可见。
    return AnimatedBuilder(
      animation: session,
      builder: (BuildContext context, Widget? _) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Row(
                children: <Widget>[
                  AnimatedBuilder(
                    animation: session,
                    builder: (_, _) => StatusChip(state: session.ws.state),
                  ),
                  const SizedBox(width: 8),
                  ValueListenableBuilder<String>(
                    valueListenable: session.hint,
                    builder: (_, String hint, _) => Expanded(
                      child: Text(
                        hint,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          color: GalPalette.of(context).textDim,
                          fontSize: 11,
                        ),
                      ),
                    ),
                  ),
                  IconButton(
                    icon: Icon(
                      Icons.history,
                      color: GalPalette.of(context).accent,
                      size: 19,
                    ),
                    tooltip: '对话历史（新页面）',
                    onPressed: () =>
                        Navigator.of(context).pushNamed(AppRoutes.history),
                  ),
                  IconButton(
                    icon: Icon(
                      Icons.tune,
                      color: GalPalette.of(context).accent,
                      size: 20,
                    ),
                    tooltip: '设定（新页面）',
                    onPressed: () =>
                        Navigator.of(context).pushNamed(AppRoutes.settings),
                  ),
                ],
              ),
              if (AppConfig.showFps ||
                  AppConfig.cameraEnabled ||
                  AppConfig.reduceAnimations ||
                  session.powerSave.value ||
                  session.staticMode.value ||
                  session.overlayOn.value)
                Padding(
                  padding: const EdgeInsets.only(top: 2, left: 2),
                  child: Row(
                    children: <Widget>[
                      if (AppConfig.showFps)
                        ValueListenableBuilder<double>(
                          valueListenable: session.fps,
                          builder: (_, double fps, _) => _Tag(
                            '${fps.toStringAsFixed(0)}fps / ${AppConfig.targetFps}',
                            GalPalette.of(context).accent,
                          ),
                        ),
                      if (AppConfig.reduceAnimations)
                        _Tag('减少动画', GalPalette.of(context).textDim),
                      if (session.overlayOn.value)
                        _Tag('置顶浮窗 · 右侧探头', GalPalette.of(context).online),
                      if (AppConfig.cameraEnabled)
                        _Tag('相机实时背景', GalPalette.of(context).accentSoft),
                      const SizedBox(width: 6),
                      AnimatedBuilder(
                        animation: session,
                        builder: (_, _) => Text(
                          '${AppConfig.activeModel.name} · ${AppConfig.quality.name}',
                          style: TextStyle(
                            color: GalPalette.of(context).textFaint,
                            fontSize: 10,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Tag extends StatelessWidget {
  const _Tag(this.label, this.color);
  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(right: 6),
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: GalPalette.of(context).dialog.withValues(alpha: .9),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: .6)),
      ),
      child: Text(label, style: TextStyle(color: color, fontSize: 9)),
    );
  }
}
