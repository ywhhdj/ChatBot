import 'dart:async';

import 'package:ar_live2d_agent/app/stage_session.dart';
import 'package:flutter/material.dart';

import '../app/stage_scope.dart';
import '../core/config/stage_config.dart';
import 'debug_bus.dart';

/// 调试 HUD：IgnorePointer+ RepaintBoundary + 4Hz 局部刷新（U58）。
class DebugHud extends StatefulWidget {
  const DebugHud({super.key});

  @override
  State<DebugHud> createState() => _DebugHudState();
}

class _DebugHudState extends State<DebugHud> {
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(
      Duration(milliseconds: 1000 ~/ StageConfig.hudRefreshHz),
      (_) {
        if (mounted) setState(() {});
      },
    );
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final StageSession session = StageScope.of(context);
    final DebugBus bus = DebugBus.instance;
    return Positioned(
      right: 10,
      bottom: 190,
      child: IgnorePointer(
        child: RepaintBoundary(
          child: Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: Colors.black.withOpacity(.68),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Text('DEBUG${bus.isMock ? " / MOCK" : ""}',
                    style: const TextStyle(
                        color: Colors.yellowAccent, fontSize: 10)),
                Text('ws: ${session.ws.state.name}  cid: ${session.ws.clientId.length}',
                    style: const TextStyle(color: Colors.white70, fontSize: 10)),
                Text('state: ${session.machine.snapshotName}  seq: ${session.machine.seq}',
                    style: const TextStyle(color: Colors.white70, fontSize: 10)),
                Text('frames: ${bus.frames.length}  bytes: ${bus.totalBytes}',
                    style: const TextStyle(color: Colors.white70, fontSize: 10)),
                Text('model: ${session.live2d.ready ? "ready" : "fallback"}  '
                    'fps: ${bus.fps}',
                    style: const TextStyle(color: Colors.white70, fontSize: 10)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
