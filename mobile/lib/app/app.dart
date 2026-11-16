import 'package:flutter/material.dart';

import '../pages/scan_page.dart';
import 'gal_palette.dart';
import 'routes.dart';
import 'session_holder.dart';
import 'stage_scope.dart';

/// 应用壳：最外层按当前色系重建 MaterialApp.theme，内层 GalThemeScope
/// 让所有命名路由页都能通过 `GalPalette.of(context)` 订阅色系变化。
class ArAgentApp extends StatefulWidget {
  const ArAgentApp({super.key});

  @override
  State<ArAgentApp> createState() => _ArAgentAppState();
}

class _ArAgentAppState extends State<ArAgentApp> with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.detached) {
      SessionHolder.instance.stopOverlay();
    }
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
            theme: paletteFor(scheme).theme(),
            home: const ScanPage(),
            onGenerateRoute: AppRoutes.onGenerateRoute,
          ),
        ),
      ),
    );
  }
}
