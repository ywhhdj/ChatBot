import 'package:flutter/material.dart';

import '../app/session_holder.dart';
import '../app/stage_scope.dart';
import '../components/stage/stage_view.dart';

/// 路由级页面：只把扫码/手输得到的地址写入全局会话并启动一次，
/// 不创建也不销毁服务（设置页 / 历史页 / 悬浮窗都要继续用同一个 session）。
class StagePage extends StatefulWidget {
  const StagePage({super.key, required this.wsUrl, this.pairUid = ''});

  final String wsUrl;
  final String pairUid;

  @override
  State<StagePage> createState() => _StagePageState();
}

class _StagePageState extends State<StagePage> {
  @override
  void initState() {
    super.initState();
    final session = SessionHolder.instance;
    session.configureEndpoint(widget.wsUrl, widget.pairUid);
    session.start();
  }

  @override
  Widget build(BuildContext context) {
    return StageScope(
      session: SessionHolder.instance,
      child: StageView(session: SessionHolder.instance),
    );
  }
}
