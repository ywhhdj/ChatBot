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
    // 原来订阅整个 session：任何 WS / 输入 / 刷新通知都会重建整个状态栏，
    // 刷新模型时就会「闪一下」。改为只订阅 modelRevision 与 visualRevision：
    // 前者管模型状态，后者让「显示帧率 / 相机 / 减少动画」等开关改动即时生效
    // （applyParams 只递增 visualRevision，不广播整个 session）。
    // 嵌套订阅而不是每次 build 都 new 一个 Listenable.merge：
    // merge 对象每次都变会让 AnimatedBuilder 反复注销/注册监听。
    return ValueListenableBuilder<int>(
      valueListenable: session.modelRevision,
      builder: (BuildContext context, int _, Widget? outerChild) =>
          ValueListenableBuilder<int>(
        valueListenable: session.visualRevision,
        builder: (BuildContext context, int _, Widget? innerChild) => SafeArea(
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
                      onPressed: () => AppRoutes.pushOnce(
                        context,
                        AppRoutes.history,
                      ),
                    ),
                    IconButton(
                      icon: Icon(
                        Icons.tune,
                        color: GalPalette.of(context).accent,
                        size: 20,
                      ),
                      tooltip: '设定（新页面）',
                      onPressed: () => AppRoutes.pushOnce(
                        context,
                        AppRoutes.settings,
                      ),
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
                        Text(
                          '${AppConfig.activeModel.name} · ${AppConfig.quality.name}',
                          style: TextStyle(
                            color: GalPalette.of(context).textFaint,
                            fontSize: 10,
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
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
