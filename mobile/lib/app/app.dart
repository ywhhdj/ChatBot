import 'package:flutter/material.dart';

import '../pages/scan_page.dart';
import 'routes.dart';
import 'theme.dart';

class ArAgentApp extends StatelessWidget {
  const ArAgentApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AR Live2D Agent',
      debugShowCheckedModeBanner: false,
      theme: galgameTheme,
      home: const ScanPage(),
      onGenerateRoute: AppRoutes.onGenerateRoute,
    );
  }
}
