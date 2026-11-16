import 'dart:async';

import 'package:flutter/material.dart';

import '../pages/scan_page.dart';
import '../services/storage/prefs.dart';
import 'gal_palette.dart';
import 'routes.dart';
import 'session_holder.dart';
import 'stage_scope.dart';

/// 应用壳：最外层按当前色系重建 MaterialApp.theme，内层 GalThemeScope
/// 让所有命名路由页都能通过 `GalPalette.of(context)` 订阅色系变化。
///
/// 主题实例按色系缓存：原来每次 build 都 new 一个 ThemeData，
/// 会在任何外层重建时触发 AnimatedTheme 过渡，视觉上就是「闪一下」。
class ArAgentApp extends StatefulWidget {
  const ArAgentApp({super.key});

  @override
  State<ArAgentApp> createState() => _ArAgentAppState();
}

class _ArAgentAppState extends State<ArAgentApp> with WidgetsBindingObserver {
  static final Map<GalScheme, ThemeData> _themes = <GalScheme, ThemeData>{
    for (final GalScheme s in GalScheme.values) s: paletteFor(s).theme(),
  };

  bool _shuttingDown = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.detached) {
      // 退出时必须释放 WebSocket / 姿态 / 语音 / Live2D controller，
      // 并补写防抖窗口里没落盘的设置与历史。
      unawaited(_shutdown());
    }
  }

  Future<void> _shutdown() async {
    if (_shuttingDown) return;
    _shuttingDown = true;
    try {
      await SessionHolder.instance.dispose();
    } catch (_) {}
    try {
      await Prefs.flush();
    } catch (_) {}
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<GalScheme>(
      valueListenable: GalPalette.scheme,
      builder: (BuildContext context, GalScheme scheme, Widget? _) =>
          GalThemeScope(
        scheme: GalPalette.scheme,
        child: StageScope(
          session: SessionHolder.instance,
          child: MaterialApp(
            title: 'AR Live2D Agent',
            debugShowCheckedModeBanner: false,
            theme: _themes[scheme],
            home: const ScanPage(),
            onGenerateRoute: AppRoutes.onGenerateRoute,
          ),
        ),
      ),
    );
  }
}
