import 'package:flutter/material.dart';

import '../pages/stage_page.dart';

/// 路由表：pages 之间不互相 import，统一走命名路由。
class AppRoutes {
  static const String stage = '/stage';

  static Route<dynamic>? onGenerateRoute(RouteSettings settings) {
    if (settings.name == stage) {
      final String wsUrl = settings.arguments is String
          ? settings.arguments! as String
          : '';
      return MaterialPageRoute<dynamic>(
        builder: (_) => StagePage(wsUrl: wsUrl),
        settings: settings,
      );
    }
    return null;
  }
}
