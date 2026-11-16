import 'package:flutter/material.dart';

import '../../app/gal_palette.dart';
import '../../app/routes.dart';
import '../../app/stage_scope.dart';
import '../../core/config/app_config.dart';
import '../../core/config/stage_config.dart';
import '../common/draggable_panel.dart';
import 'typewriter_text.dart';

/// Galgame 对话框：名牌、逐字机、点击继续、选项、历史入口、Skip。
///
/// * 可水平拖动，向右拖过阈值收进右缘变成「←」箭头，并进入静态省电；
/// * Live2D 置顶浮窗模式下自动缩到右侧 62% 宽、隐藏选项，不遮挡其他应用。
class DialogLayer extends StatefulWidget {
  const DialogLayer({super.key});

  @override
  State<DialogLayer> createState() => _DialogLayerState();
}

class _DialogLayerState extends State<DialogLayer> {
  final GlobalKey<TypewriterTextState> _typeKey =
      GlobalKey<TypewriterTextState>();

  static const List<String> _choices = <String>[
    '今天也来陪我吗？',
    '刚才那一下，是你在闹别扭吗？',
    '给我讲讲你那边的事吧',
  ];

  @override
  Widget build(BuildContext context) {
    final session = StageScope.of(context);
    final GalPaletteData p = GalPalette.of(context);
    // visualRevision 变更（含「关闭逐字机」开关）会重建子树，
    // TypewriterText.didUpdateWidget 才会同步新标志。
    return ValueListenableBuilder<int>(
      valueListenable: session.visualRevision,
      builder: (BuildContext context, int _, Widget? _) =>
          ValueListenableBuilder<bool>(
            valueListenable: session.overlayOn,
            builder: (BuildContext context, bool overlay, Widget? _) =>
                DraggablePanel(
                  panelId: 'dialog',
                  onHiddenChanged: session.setPanelHidden,
                  alignment: overlay
                      ? Alignment.bottomRight
                      : Alignment.bottomCenter,
                  widthFactor: overlay ? 0.62 : 1.0,
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    child: GestureDetector(
                      onTap: () => _typeKey.currentState?.skip(),
                      child: Container(
                        width: double.infinity,
                        constraints: BoxConstraints(
                          minHeight: overlay ? 96 : 132,
                        ),
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: p.dialog.withValues(
                            alpha: StageConfig.dialogOpacity,
                          ),
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(color: p.border, width: 1.2),
                          boxShadow: <BoxShadow>[
                            BoxShadow(
                              color: p.glow,
                              blurRadius: 18,
                              spreadRadius: -10,
                            ),
                          ],
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          mainAxisSize: MainAxisSize.min,
                          children: <Widget>[
                            Row(
                              children: <Widget>[
                                AnimatedBuilder(
                                  animation: session,
                                  builder: (_, _) => Text(
                                    AppConfig.characterName,
                                    style: TextStyle(
                                      color: p.accent,
                                      fontSize: 15,
                                      fontWeight: FontWeight.bold,
                                      letterSpacing: 1.2,
                                    ),
                                  ),
                                ),
                                const Spacer(),
                                Tooltip(
                                  message: '向右拖动可收起 · 自动静态省电',
                                  child: Icon(
                                    Icons.drag_indicator,
                                    color: p.textFaint,
                                    size: 14,
                                  ),
                                ),
                                IconButton(
                                  icon: Icon(
                                    Icons.history,
                                    color: p.textDim,
                                    size: 18,
                                  ),
                                  onPressed: () =>
                                      Navigator.of(context)
                                          .pushNamed(AppRoutes.history),
                                  tooltip: '对话历史（新页面）',
                                ),
                              ],
                            ),
                            const SizedBox(height: 8),
                            ValueListenableBuilder<String>(
                              valueListenable: session.dialogText,
                              builder: (_, String text, _) => TypewriterText(
                                key: _typeKey,
                                text: text.isEmpty ? '……' : text,
                              ),
                            ),
                            if (!overlay) ...<Widget>[
                              const SizedBox(height: 10),
                              Wrap(
                                spacing: 8,
                                children: <Widget>[
                                  for (final String c in _choices)
                                    ActionChip(
                                      backgroundColor: p.card,
                                      side: BorderSide(color: p.borderSoft),
                                      label: Text(
                                        c,
                                        style: TextStyle(
                                          color: p.textDim,
                                          fontSize: 11,
                                        ),
                                      ),
                                      onPressed: () => session.sendText(c),
                                    ),
                                ],
                              ),
                            ],
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
          ),
    );
  }
}
