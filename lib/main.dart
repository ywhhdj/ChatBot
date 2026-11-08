import 'pages/Scan.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
  runApp(const ArAgentApp());
}

class ArAgentApp extends StatelessWidget {
  const ArAgentApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AR Live2D Agent',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark(),
      home: const ScanPage(),   // ← 改成扫码页
    );
  }
}