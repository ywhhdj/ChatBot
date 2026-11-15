import 'package:ar_live2d_agent/app/stage_session.dart';
import 'package:flutter/material.dart';

import '../../app/stage_scope.dart';
import '../../core/config/app_config.dart';
import '../../core/config/stage_config.dart';
import 'typewriter_text.dart';
import 'history_layer.dart';

/// Galgame 对话框：名牌、逐字机、点击继续、选项、历史、Skip（S6.2）。
class DialogLayer extends StatelessWidget {
  const DialogLayer({super.key});

  static const List<String> _choices = <String>[
    '今天也来陪我吗？',
    '刚才那一下，是你在闹别扭吗？',
    '给我讲讲你那边的事吧',
  ];

  @override
  Widget build(BuildContext context) {
    final StageSession session = StageScope.of(context);
    final GlobalKey<TypewriterTextState> typeKey = GlobalKey<TypewriterTextState>();

    return Align(
      alignment: Alignment.bottomCenter,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 0, 12, 96),
        child: GestureDetector(
          onTap: () => typeKey.currentState?.skip(),
          child: Container(
            width: double.infinity,
            constraints: const BoxConstraints(minHeight: 132),
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: const Color(0xFF120B1A).withOpacity(StageConfig.dialogOpacity),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: Colors.white24),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    Text(AppConfig.characterName,
                        style: const TextStyle(
                            color: Color(0xFFE9B8FF),
                            fontSize: 15,
                            fontWeight: FontWeight.bold)),
                    const Spacer(),
                    IconButton(
                      icon: const Icon(Icons.history, color: Colors.white54, size: 18),
                      onPressed: () => showDialog<void>(
                        context: context,
                        builder: (_) => const HistoryLayer(),
                      ),
                      tooltip: '对话历史',
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                ValueListenableBuilder<String>(
                  valueListenable: session.dialogText,
                  builder: (_, String text, __) => TypewriterText(
                    key: typeKey,
                    text: text.isEmpty ? '……' : text,
                  ),
                ),
                const SizedBox(height: 10),
                Wrap(
                  spacing: 8,
                  children: <Widget>[
                    for (final String c in _choices)
                      ActionChip(
                        label: Text(c, style: const TextStyle(fontSize: 11)),
                        onPressed: () => session.sendText(c),
                      ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
