import 'package:ar_live2d_agent/app/stage_session.dart';
import 'package:flutter/material.dart';

import '../../app/stage_scope.dart';
import '../../core/config/app_config.dart';

/// 对话历史：内存环形队列上限 100 条、不落库、可清空（U41）。
class HistoryLayer extends StatelessWidget {
  const HistoryLayer({super.key});

  @override
  Widget build(BuildContext context) {
    final StageSession session = StageScope.of(context);
    return AlertDialog(
      backgroundColor: const Color(0xFF1B1026),
      title: const Text('对话历史',
          style: TextStyle(color: Colors.white, fontSize: 16)),
      content: SizedBox(
        width: double.maxFinite,
        child: ListView.builder(
          shrinkWrap: true,
          itemCount: session.history.length > AppConfig.maxHistoryItems
              ? AppConfig.maxHistoryItems
              : session.history.length,
          itemBuilder: (_, int i) => ListTile(
            dense: true,
            title: Text(session.history[i],
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: Colors.white70, fontSize: 12)),
          ),
        ),
      ),
      actions: <Widget>[
        TextButton(
          onPressed: () {
            session.history.clear();
            Navigator.of(context).pop();
          },
          child: const Text('清空'),
        ),
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('关闭'),
        ),
      ],
    );
  }
}
