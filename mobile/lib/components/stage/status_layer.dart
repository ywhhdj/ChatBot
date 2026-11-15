import 'package:ar_live2d_agent/app/stage_session.dart';
import 'package:flutter/material.dart';

import '../../app/stage_scope.dart';
import '../../core/config/app_config.dart';
import '../common/status_chip.dart';
import '../settings/settings_sheet.dart';

/// 三态连接状态 + 当前模型/档位 + 设定入口（U42）。
class StatusLayer extends StatelessWidget {
  const StatusLayer({super.key});

  @override
  Widget build(BuildContext context) {
    final StageSession session = StageScope.of(context);
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        child: Row(
          children: <Widget>[
            StatusChip(state: session.ws.state),
            const SizedBox(width: 8),
            ValueListenableBuilder<String>(
              valueListenable: session.hint,
              builder: (_, String hint, __) => Expanded(
                child: Text(hint,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: Colors.white60, fontSize: 11)),
              ),
            ),
            Text(AppConfig.activeModel.name,
                style: const TextStyle(color: Colors.white54, fontSize: 11)),
            const SizedBox(width: 6),
            Text(AppConfig.quality.name,
                style: const TextStyle(color: Colors.white38, fontSize: 11)),
            IconButton(
              icon: const Icon(Icons.tune, color: Colors.white70, size: 20),
              tooltip: '设定',
              onPressed: () => showModalBottomSheet<void>(
                context: context,
                backgroundColor: Colors.transparent,
                builder: (_) => const SettingsSheet(),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
