import 'package:flutter/material.dart';

import '../app/stage_scope.dart';
import '../app/stage_session.dart';
import '../components/stage/stage_view.dart';

/// 路由级页面：只创建会话、装配 Scope，任何 UI 都在 components/。
class StagePage extends StatefulWidget {
  const StagePage({super.key, required this.wsUrl});

  final String wsUrl;

  @override
  State<StagePage> createState() => _StagePageState();
}

class _StagePageState extends State<StagePage> {
  late final StageSession _session;

  @override
  void initState() {
    super.initState();
    _session = StageSession(wsUrl: widget.wsUrl);
    _session.start();
  }

  @override
  void dispose() {
    _session.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return StageScope(
        session: _session, child: StageView(session: _session));
  }
}
