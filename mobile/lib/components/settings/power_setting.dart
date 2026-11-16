import 'package:flutter/material.dart';

import '../../app/gal_palette.dart';
import '../../app/stage_session.dart';
import '../../core/config/app_config.dart';
import '../../services/platform/overlay_channel.dart';
import '../../services/storage/prefs.dart';
import '../common/retry_hint.dart';
import '../common/section_card.dart';

/// 帧率 / 后台省电 / 置顶悬浮窗。
///
/// 规则：切到后台默认「几乎无帧」（Ticker、姿态、相机、模型全停）；
/// 只有开启并成功启动「Live2D 模型所有应用置顶」悬浮窗时，后台仍以低帧率渲染。
class PowerSetting extends StatefulWidget {
  const PowerSetting({super.key, required this.session});

  final StageSession session;

  @override
  State<PowerSetting> createState() => _PowerSettingState();
}

class _PowerSettingState extends State<PowerSetting> {
  static const List<int> _fpsOptions = <int>[24, 30, 45, 60, 90, 120];
  bool _busy = false;
  String _overlayHint = '';

  Future<void> _commit() async {
    Prefs.scheduleSave();
    widget.session.applyParams();
  }

  Future<void> _toggleOverlay(bool value) async {
    if (_busy) return;
    setState(() => _busy = true);
    AppConfig.overlayEnabled = value;
    Prefs.scheduleSave();
    if (value) {
      if (!widget.session.live2d.ready) {
        _overlayHint = '当前是占位立绘，建议先在「模型」页加载模型再开启置顶';
      }
      final bool ok = await widget.session.startOverlay();
      if (!ok && await OverlayChannel.available()) {
        _overlayHint = '请重试：需要「显示在其他应用上层」权限';
      } else if (!ok) {
        _overlayHint = '此平台不支持跨应用置顶（iOS 可在应用内使用）';
      } else {
        _overlayHint = '置顶浮窗已开启 · 后台保持低帧率演出';
      }
    } else {
      await widget.session.stopOverlay();
      _overlayHint = '置顶浮窗已关闭 · 后台恢复自动省电';
    }
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    final StageSession session = widget.session;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        SectionCard(
          title: '舞台帧率',
          children: <Widget>[
            Text(
              '限制舞台 Ticker 的实际重建频率；低档机可降到 24/30fps 省电。',
              style: TextStyle(
                color: GalPalette.of(context).textDim,
                fontSize: 11,
              ),
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 6,
              children: <Widget>[
                for (final int f in _fpsOptions)
                  ChoiceChip(
                    label: Text(
                      '${f}fps',
                      style: TextStyle(
                        fontSize: 11,
                        color: AppConfig.targetFps == f
                            ? GalPalette.of(context).scaffold
                            : GalPalette.of(context).textDim,
                      ),
                    ),
                    selected: AppConfig.targetFps == f,
                    selectedColor: GalPalette.of(context).accent,
                    backgroundColor: GalPalette.of(context).card,
                    side: BorderSide(color: GalPalette.of(context).borderSoft),
                    onSelected: (_) async {
                      setState(() => AppConfig.targetFps = f);
                      await _commit();
                    },
                  ),
              ],
            ),
            const SizedBox(height: 10),
            ValueListenableBuilder<double>(
              valueListenable: session.fps,
              builder: (_, double fps, _) => Text(
                '实测帧率：${fps.toStringAsFixed(1)} fps',
                style: TextStyle(
                  color: GalPalette.of(context).accent,
                  fontSize: 12,
                ),
              ),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              dense: true,
              activeColor: GalPalette.of(context).accent,
              title: Text(
                '状态栏显示实时帧率',
                style: TextStyle(
                  color: GalPalette.of(context).textDim,
                  fontSize: 11,
                ),
              ),
              value: AppConfig.showFps,
              onChanged: (bool v) async {
                setState(() => AppConfig.showFps = v);
                await _commit();
              },
            ),
          ],
        ),
        SectionCard(
          title: '后台自动省电',
          children: <Widget>[
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              dense: true,
              activeColor: GalPalette.of(context).accent,
              title: Text(
                '切到后台时几乎无帧',
                style: TextStyle(
                  color: GalPalette.of(context).textDim,
                  fontSize: 11,
                ),
              ),
              subtitle: Text(
                '停 Ticker / 姿态 / 相机 / Live2D，只保留静态画面；回前台自动恢复。',
                style: TextStyle(
                  color: GalPalette.of(context).textFaint,
                  fontSize: 10,
                ),
              ),
              value: AppConfig.powerSaveEnabled,
              onChanged: (bool v) async {
                setState(() => AppConfig.powerSaveEnabled = v);
                await _commit();
              },
            ),
            ValueListenableBuilder<bool>(
              valueListenable: session.powerSave,
              builder: (_, bool saving, _) => Text(
                saving ? '当前：省电中（几乎无帧）' : '当前：前台正常演出',
                style: TextStyle(
                  color: saving
                      ? GalPalette.of(context).busy
                      : GalPalette.of(context).online,
                  fontSize: 11,
                ),
              ),
            ),
          ],
        ),
        SectionCard(
          title: '减少动画',
          children: <Widget>[
            Text(
              '开启后关闭界面切换类动画：页面转场、设定分区滑动、卡片淡入、'
              '面板展开/收起都瞬时完成。逐字机属于台词演出，**默认不关**，'
              '需要时才用下面的独立开关；Live2D 立绘演出与舞台帧率始终保留。',
              style: TextStyle(
                color: GalPalette.of(context).textDim,
                fontSize: 11,
              ),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              dense: true,
              activeColor: GalPalette.of(context).accent,
              title: Text(
                '减少动画（除 Live2D 与逐字机外）',
                style: TextStyle(
                  color: GalPalette.of(context).textDim,
                  fontSize: 11,
                ),
              ),
              value: AppConfig.reduceAnimations,
              onChanged: (bool v) async {
                setState(() => AppConfig.reduceAnimations = v);
                await _commit();
              },
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              dense: true,
              activeColor: GalPalette.of(context).accent,
              title: Text(
                '关闭逐字机（默认关 = 保留逐字演出）',
                style: TextStyle(
                  color: GalPalette.of(context).textDim,
                  fontSize: 11,
                ),
              ),
              subtitle: Text(
                '只有明确打开才让台词一次性全显；与「减少动画」互不影响。',
                style: TextStyle(
                  color: GalPalette.of(context).textFaint,
                  fontSize: 10,
                ),
              ),
              value: AppConfig.disableTypewriter,
              onChanged: (bool v) async {
                setState(() => AppConfig.disableTypewriter = v);
                await _commit();
              },
            ),
          ],
        ),
        SectionCard(
          title: 'Live2D 模型所有应用置顶（悬浮窗）',
          children: <Widget>[
            Text(
              '开启后模型浮在其他应用之上；这是唯一不进入后台省电的例外，'
              '此时以低帧率（默认 15fps）继续渲染。Android 需要「显示在其他应用上层」权限。',
              style: TextStyle(
                color: GalPalette.of(context).textDim,
                fontSize: 11,
              ),
            ),
            const SizedBox(height: 10),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              dense: true,
              activeColor: GalPalette.of(context).accent,
              title: Text(
                '启用置顶浮窗',
                style: TextStyle(
                  color: GalPalette.of(context).textDim,
                  fontSize: 11,
                ),
              ),
              value: AppConfig.overlayEnabled,
              onChanged: _busy ? null : _toggleOverlay,
            ),
            ValueListenableBuilder<bool>(
              valueListenable: session.overlayOn,
              builder: (_, bool on, _) => Text(
                on ? '浮窗运行中 · 后台 ${AppConfig.overlayFps}fps' : '浮窗未运行',
                style: TextStyle(
                  color: on
                      ? GalPalette.of(context).online
                      : GalPalette.of(context).textFaint,
                  fontSize: 11,
                ),
              ),
            ),
            const SizedBox(height: 6),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              dense: true,
              activeColor: GalPalette.of(context).accent,
              title: Text(
                '置定时缩小在右侧 · 默认右侧探头',
                style: TextStyle(
                  color: GalPalette.of(context).textDim,
                  fontSize: 11,
                ),
              ),
              subtitle: Text(
                '避免遮挡其他应用，又不会完全看不见模型；关闭则保持原尺寸。',
                style: TextStyle(
                  color: GalPalette.of(context).textFaint,
                  fontSize: 10,
                ),
              ),
              value: AppConfig.overlayPeekEnabled,
              onChanged: (bool v) async {
                setState(() => AppConfig.overlayPeekEnabled = v);
                await _commit();
                await widget.session.refreshOverlayAppearance();
              },
            ),
            const SizedBox(height: 4),
            Text(
              '模型缩放',
              style: TextStyle(
                color: GalPalette.of(context).textDim,
                fontSize: 11,
              ),
            ),
            const SizedBox(height: 6),
            Wrap(
              spacing: 8,
              children: <Widget>[
                for (final double s in <double>[0.4, 0.55, 0.7, 0.85])
                  ChoiceChip(
                    label: Text(
                      '${(s * 100).round()}%',
                      style: TextStyle(
                        fontSize: 11,
                        color: (AppConfig.overlayScale - s).abs() < 0.01
                            ? GalPalette.of(context).scaffold
                            : GalPalette.of(context).textDim,
                      ),
                    ),
                    selected: (AppConfig.overlayScale - s).abs() < 0.01,
                    selectedColor: GalPalette.of(context).accent,
                    backgroundColor: GalPalette.of(context).card,
                    side: BorderSide(color: GalPalette.of(context).borderSoft),
                    onSelected: (_) async {
                      setState(() => AppConfig.overlayScale = s);
                      await _commit();
                      await widget.session.refreshOverlayAppearance();
                    },
                  ),
              ],
            ),
            if (_overlayHint.isNotEmpty) ...<Widget>[
              const SizedBox(height: 8),
              RetryHint(
                compact: true,
                title: '浮窗状态',
                detail: _overlayHint,
                actionLabel: '请重试',
                onRetry: () => _toggleOverlay(true),
              ),
            ],
            const SizedBox(height: 8),
            Text(
              '悬浮窗里的 Live2D 渲染需要原生纹理桥接；当前原生侧提供可拖动浮窗视图，'
              'Dart 侧持续以低帧率驱动舞台状态。',
              style: TextStyle(
                color: GalPalette.of(context).textFaint,
                fontSize: 10,
              ),
            ),
          ],
        ),
      ],
    );
  }
}
