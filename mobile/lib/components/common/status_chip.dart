import 'package:flutter/material.dart';

import '../../core/net/ws_service.dart';

/// 三态状态胶囊（U42）：connected / reconnecting / offline。
class StatusChip extends StatelessWidget {
  const StatusChip({super.key, required this.state});

  final WsState state;

  @override
  Widget build(BuildContext context) {
    final Color color;
    final String label;
    switch (state) {
      case WsState.connected:
        color = Colors.greenAccent;
        label = '在线';
        break;
      case WsState.connecting:
      case WsState.reconnecting:
        color = Colors.orangeAccent;
        label = '重连中';
        break;
      case WsState.offline:
        color = Colors.redAccent;
        label = '离线 / 单机';
        break;
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: Colors.black54,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(Icons.circle, size: 9, color: color),
          const SizedBox(width: 6),
          Text(label, style: const TextStyle(color: Colors.white, fontSize: 11)),
        ],
      ),
    );
  }
}
