import 'package:flutter/material.dart';

import '../../app/gal_palette.dart';
import '../../core/net/ws_service.dart';

/// 三态状态胶囊：connected / reconnecting / offline。
class StatusChip extends StatelessWidget {
  const StatusChip({super.key, required this.state});

  final WsState state;

  @override
  Widget build(BuildContext context) {
    final Color color;
    final String label;
    switch (state) {
      case WsState.connected:
        color = GalPalette.of(context).online;
        label = '在线';
        break;
      case WsState.connecting:
      case WsState.reconnecting:
        color = GalPalette.of(context).busy;
        label = '重连中';
        break;
      case WsState.offline:
        color = GalPalette.of(context).offline;
        label = '离线 / 单机';
        break;
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: GalPalette.of(context).dialog.withValues(alpha: .88),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: GalPalette.of(context).borderSoft),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(Icons.circle, size: 9, color: color),
          const SizedBox(width: 6),
          Text(
            label,
            style: TextStyle(color: GalPalette.of(context).text, fontSize: 11),
          ),
        ],
      ),
    );
  }
}
