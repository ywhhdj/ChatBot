import 'package:flutter/material.dart';

import '../../debug/debug_flags.dart';
import '../../debug/debug_panel.dart';
import '../common/section_card.dart';
import 'connection_setting.dart';
import 'model_setting.dart';

/// Galgame 设定面板。开发者分区的实现只住 debug/，这里仅编译期分支挂载（S9.2）。
class SettingsSheet extends StatelessWidget {
  const SettingsSheet({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: Color(0xFF120B1A),
        borderRadius: BorderRadius.vertical(top: Radius.circular(18)),
      ),
      padding: const EdgeInsets.fromLTRB(16, 20, 16, 28),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            const Center(
              child: Text('设 定',
                  style: TextStyle(color: Colors.white, fontSize: 17)),
            ),
            const SizedBox(height: 16),
            const ModelSetting(),
            const ConnectionSetting(),
            if (kStageDebug) const _DeveloperSection(),
          ],
        ),
      ),
    );
  }
}

class _DeveloperSection extends StatelessWidget {
  const _DeveloperSection();

  @override
  Widget build(BuildContext context) {
    return SectionCard(
      title: '开发者（仅 debug 构建可见）',
      children: <Widget>[
        // 调试面板本体来自 debug/ 目录。
        const DebugPanel(),
      ],
    );
  }
}
