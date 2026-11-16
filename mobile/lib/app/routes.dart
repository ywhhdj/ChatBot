import 'package:flutter/material.dart';

import '../core/config/route_guard.dart';
import '../core/net/ws_url.dart';
import '../pages/connect_page.dart';
import '../pages/history_page.dart';
import '../pages/settings_page.dart';
import '../pages/stage_page.dart';
import 'motion.dart';

/// 路由表：设置 / 历史 / 连接
/// 「减少动画」开启时转场零时长、无淡入，Live2D 演出不受影响。
class AppRoutes {
  static const String stage = '/stage';
  static const String settings = '/settings';
  static const String history = '/history';
  static const String connect = '/connect';

  /// 同名路由同时只允许一条：连点 / 刷新期间重复 push 会叠出多层页面，
  /// 返回时用户看到的就是「设置页一闪而过」。
  static Future<T?> pushOnce<T extends Object?>(
    BuildContext context,
    String name, {
    Object? arguments,
  }) async {
    if (!RouteGuard.tryEnter(name)) return null;
    try {
      return await Navigator.of(context).pushNamed<T>(
        name,
        arguments: arguments,
      );
    } finally {
      RouteGuard.leave(name);
    }
  }

  static Route<dynamic>? onGenerateRoute(RouteSettings settings) {
    final Object? args = settings.arguments;
    String wsUrl = '';
    String pairUid = '';
    if (args is WsEndpoint) {
      wsUrl = args.url;
      pairUid = args.uid;
    } else if (args is String) {
      wsUrl = args;
    }

    switch (settings.name) {
      case stage:
        return _page(StagePage(wsUrl: wsUrl, pairUid: pairUid), settings);
      case AppRoutes.settings:
        return _page(const SettingsPage(), settings);
      case history:
        return _page(const HistoryPage(), settings);
      case connect:
        return _page(const ConnectPage(), settings);
      default:
        return null;
    }
  }

  static Route<dynamic> _page(
    Widget child,
    RouteSettings settings,
  ) => PageRouteBuilder<dynamic>(
    settings: settings,
    transitionDuration: Motion.page,
    reverseTransitionDuration: Motion.page,
    pageBuilder: (_, _, _) => child,
    transitionsBuilder: (
      BuildContext context,
      Animation<double> animation,
      Animation<double> secondary,
      Widget page,
    ) => Motion.off ? page : FadeTransition(opacity: animation, child: page),
  );
}
