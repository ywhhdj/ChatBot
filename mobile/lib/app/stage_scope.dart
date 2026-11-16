import 'package:flutter/widgets.dart';

import 'stage_session.dart';

/// 组件通过它读 session，不直接构造服务。
///
/// 现在 StageScope 挂在 MaterialApp 外层（app/app.dart），**所有命名路由页**
/// 都在子树内；设置 / 历史 / 连接是独立页面，也不再依赖弹层 context。
/// 这里仍保留 `maybeOf()` 安全返回 null、`of()` 抛可读错误，
/// 防止未来有人把组件挂到独立 Overlay 时 release 下空指针崩溃。
class StageScope extends InheritedNotifier<StageSession> {
  const StageScope({
    super.key,
    required StageSession session,
    required super.child,
  }) : super(notifier: session);

  static StageSession? maybeOf(BuildContext context) {
    final StageScope? scope =
        context.dependOnInheritedWidgetOfExactType<StageScope>();
    return scope?.notifier;
  }

  static StageSession of(BuildContext context) {
    final StageSession? session = maybeOf(context);
    if (session == null) {
      throw FlutterError(
        'StageScope.of() 在 StageScope 之外被调用。\n'
        '请把页面挂在 app/app.dart 的全局 StageScope 下，或把 StageSession '
        '作为参数显式传入（例如 SettingsPage / HistoryPage 的做法）。',
      );
    }
    return session;
  }
}
