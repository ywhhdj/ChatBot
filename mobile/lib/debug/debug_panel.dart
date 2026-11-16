import 'package:flutter/material.dart';

import '../app/gal_palette.dart';
import '../app/stage_session.dart';
import 'debug_bus.dart';
import 'debug_injector.dart';
import 'debug_timeline.dart';

/// 「开发者」分区实现：只住 debug/，由 settings_sheet 在 kStageDebug 分支挂载。
/// session 显式传入（弹层不在 StageScope 子树内）。
class DebugPanel extends StatelessWidget {
  const DebugPanel({super.key, required this.session});

  final StageSession session;

  @override
  Widget build(BuildContext context) {
    final DebugInjector injector = DebugInjector(session);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        StatefulBuilder(
          builder: (BuildContext context, StateSetter setLocal) {
            final bool mock = DebugBus.instance.isMock;
            return SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(mock ? '模拟注入：开（真实帧已屏蔽）' : '模拟注入：关',
                  style: TextStyle(
                      color: GalPalette.of(context).textDim, fontSize: 12)),
              value: mock,
              activeThumbColor: GalPalette.of(context).accent,
              onChanged: (bool v) {
                injector.setMock(v);
                DebugBus.instance.setMock(v);
                setLocal(() {});
              },
            );
          },
        ),
        Wrap(
          spacing: 6,
          runSpacing: 4,
          children: <Widget>[
            for (final String a in DebugInjector.actions)
              ActionChip(
                label: Text(a, style: const TextStyle(fontSize: 10)),
                onPressed: () => injector.inject(a),
              ),
          ],
        ),
        const SizedBox(height: 10),
        const DebugTimeline(),
        const SizedBox(height: 6),
        Row(
          children: <Widget>[
            TextButton(
              onPressed: () => DebugBus.instance.clear(),
              child: const Text('清空调试缓冲'),
            ),
            Text('${DebugBus.instance.totalBytes} B',
                style: TextStyle(
                    color: GalPalette.of(context).textFaint, fontSize: 10)),
          ],
        ),
      ],
    );
  }
}
