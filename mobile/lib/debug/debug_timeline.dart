import 'package:flutter/material.dart';

import 'debug_bus.dart';

/// 按 seq 排序的演出时间线；时间标注为本地时钟、仅展示（U51）。
class DebugTimeline extends StatelessWidget {
  const DebugTimeline({super.key, this.maxLines = 8});

  final int maxLines;

  @override
  Widget build(BuildContext context) {
    final List<DebugAction> items = DebugBus.instance.actions.toList()
      ..sort((DebugAction a, DebugAction b) => a.seq.compareTo(b.seq));
    final List<DebugAction> tail = items.length > maxLines
        ? items.sublist(items.length - maxLines)
        : items;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        for (final DebugAction a in tail)
          Text('#${a.seq} ${a.action}  (本地时钟 ${a.ts % 100000})',
              style: const TextStyle(color: Colors.white70, fontSize: 10)),
      ],
    );
  }
}
