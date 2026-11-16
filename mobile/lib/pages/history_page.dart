import 'package:flutter/material.dart';

import '../app/stage_scope.dart';
import '../components/common/gal_page.dart';
import '../components/stage/history_layer.dart';

/// 对话历史：全屏新页面（不再用 showDialog）。
class HistoryPage extends StatelessWidget {
  const HistoryPage({super.key});

  @override
  Widget build(BuildContext context) {
    final session = StageScope.of(context);
    return GalPage(
      title: '对话历史',
      subtitle: '最多保留 100 条 · 自动保存在本机',
      body: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(12, 12, 12, 24),
        child: HistoryLayer(
          session: session,
          onClose: () => Navigator.of(context).maybePop(),
        ),
      ),
    );
  }
}
