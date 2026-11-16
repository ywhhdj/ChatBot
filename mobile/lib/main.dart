import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'app/app.dart';
import 'services/storage/prefs.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // 色系 / 配置在 runApp 之前读完，避免启动后 GalPalette.scheme 变化
  // 让 MaterialApp 整树重建，页面「闪一下」。
  await Prefs.ensureLoaded();
  await SystemChrome.setPreferredOrientations(<DeviceOrientation>[
    DeviceOrientation.portraitUp,
  ]);
  runApp(const ArAgentApp());
}
