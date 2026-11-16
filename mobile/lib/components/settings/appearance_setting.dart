import 'package:flutter/material.dart';

import '../../app/gal_palette.dart';
import '../../app/motion.dart';
import '../../app/stage_session.dart';
import '../../core/config/app_config.dart';
import '../../services/storage/prefs.dart';
import '../common/section_card.dart';

/// 外观分区：三套色系（黑夜 / 米白 / 蓝色）即时切换并持久化。
/// 预览卡用各自的配色画一个小对话框，所见即所得。
class AppearanceSetting extends StatefulWidget {
  const AppearanceSetting({super.key, required this.session});

  final StageSession session;

  @override
  State<AppearanceSetting> createState() => _AppearanceSettingState();
}

class _AppearanceSettingState extends State<AppearanceSetting> {
  static const List<GalScheme> _schemes = <GalScheme>[
    GalScheme.night,
    GalScheme.cream,
    GalScheme.blue,
  ];

  Future<void> _pick(GalScheme s) async {
    AppConfig.scheme = s;
    GalPalette.scheme.value = s;
    await Prefs.saveAll();
    // 背景渐变 / 相机层底色也跟着走显式刷新信号，不依赖隐式 rebuild。
    widget.session.applyParams();
    // 原生浮窗同步换色（仅 Android 真正生效）。
    await widget.session.refreshOverlayAppearance();
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final GalPaletteData p = GalPalette.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        SectionCard(
          title: '色系',
          children: <Widget>[
            Text(
              '切换后所有页面（舞台 / 设定 / 历史 / 连接 / 扫码）、对话框、'
              '状态胶囊与悬浮窗配色同步变化。',
              style: TextStyle(color: p.textDim, fontSize: 11),
            ),
            const SizedBox(height: 12),
            SizedBox(
              height: 132,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: _schemes.length,
                separatorBuilder: (_, _) => const SizedBox(width: 10),
                itemBuilder: (BuildContext context, int i) {
                  final GalScheme s = _schemes[i];
                  final GalPaletteData data = paletteFor(s);
                  final bool selected = AppConfig.scheme == s;
                  return _SchemeCard(
                    data: data,
                    selected: selected,
                    onTap: () => _pick(s),
                  );
                },
              ),
            ),
            const SizedBox(height: 10),
            Text(
              '当前：${p.name} · ${p.brightness == Brightness.light ? '亮色' : '暗色'}主题',
              style: TextStyle(color: p.accent, fontSize: 11),
            ),
          ],
        ),
        SectionCard(
          title: '动效',
          children: <Widget>[
            Text(
              '「减少动画」只关界面切换类过渡（页面转场、分区滑动、卡片淡入、逐字机）；'
              'Live2D 立绘演出与舞台帧率始终保留。开关在「省电」分区。',
              style: TextStyle(color: p.textDim, fontSize: 11),
            ),
            const SizedBox(height: 8),
            AnimatedContainer(
              duration: Motion.short,
              width: double.infinity,
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: p.card.withValues(alpha: .8),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: p.borderSoft),
              ),
              child: Text(
                AppConfig.reduceAnimations
                    ? '减少动画：开 · 切换即时完成'
                    : '减少动画：关 · 保留轻微过渡',
                style: TextStyle(color: p.text, fontSize: 11),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _SchemeCard extends StatelessWidget {
  const _SchemeCard({
    required this.data,
    required this.selected,
    required this.onTap,
  });

  final GalPaletteData data;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: Motion.short,
        width: 116,
        padding: const EdgeInsets.all(8),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: selected ? data.accent : data.borderSoft,
            width: selected ? 2 : 1,
          ),
          boxShadow: selected
              ? <BoxShadow>[BoxShadow(color: data.glow, blurRadius: 10)]
              : null,
        ),
        child: DecoratedBox(
          decoration: BoxDecoration(
            gradient: data.background,
            borderRadius: BorderRadius.circular(9),
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.end,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              const Spacer(),
              Container(
                margin: const EdgeInsets.all(6),
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 5),
                decoration: BoxDecoration(
                  color: data.dialog.withValues(alpha: .9),
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: data.border),
                ),
                child: Text(
                  data.name,
                  textAlign: TextAlign.center,
                  style: TextStyle(color: data.accent, fontSize: 10),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
