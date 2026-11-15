import 'package:flutter/widgets.dart';

import 'stage_session.dart';

/// 组件通过它读 session，不直接构造服务。
class StageScope extends InheritedNotifier<StageSession> {
  const StageScope({
    super.key,
    required StageSession session,
    required super.child,
  }) : super(notifier: session);

  static StageSession of(BuildContext context) {
    final StageScope? scope =
        context.dependOnInheritedWidgetOfExactType<StageScope>();
    assert(scope != null, 'StageScope is missing above this widget');
    return scope!.notifier!;
  }
}
