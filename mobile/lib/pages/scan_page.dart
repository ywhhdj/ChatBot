import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../app/routes.dart';
import '../core/config/app_config.dart';
import '../core/net/ws_url.dart';
import '../services/storage/prefs.dart';

class ScanPage extends StatefulWidget {
  const ScanPage({super.key});

  @override
  State<ScanPage> createState() => _ScanPageState();
}

class _ScanPageState extends State<ScanPage> {
  final MobileScannerController _scanner = MobileScannerController(
    detectionSpeed: DetectionSpeed.noDuplicates,
    facing: CameraFacing.back,
  );

  bool _handled = false;
  String? _lastUrl;

  @override
  void initState() {
    super.initState();
    _loadLastUrl();
  }

  Future<void> _loadLastUrl() async {
    final String? url = await Prefs.getLastWsUrl();
    if (url != null && mounted) setState(() => _lastUrl = url);
  }

  Future<void> _onDetect(BarcodeCapture capture) async {
    if (_handled || capture.barcodes.isEmpty) return;
    final String? raw = capture.barcodes.first.rawValue;
    final String? url = raw == null ? null : WsUrl.normalize(raw);
    if (url == null) return;
    _handled = true;
    await _closeScannerThenGo(url);
  }

  /// U47：三条跳转路径统一先停相机再走，避免相机占用导致舞台页初始化失败。
  Future<void> _closeScannerThenGo(String url) async {
    try {
      await _scanner.stop();
    } catch (_) {}
    await Prefs.setLastWsUrl(url);
    if (!mounted) return;
    AppConfig.wsUrl = url;
    await Navigator.of(context).pushReplacementNamed(
      AppRoutes.stage,
      arguments: url,
    );
  }

  void _gotoLast() {
    final String url = _lastUrl ?? '';
    if (url.isEmpty) return;
    _closeScannerThenGo(url);
  }

  void _showManualInput() {
    final TextEditingController controller = TextEditingController();
    showDialog<String>(
      context: context,
      builder: (BuildContext ctx) => AlertDialog(
        title: const Text('输入串流地址'),
        content: TextField(
          controller: controller,
          decoration: const InputDecoration(hintText: 'ws://192.168.1.10:8000/'),
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, controller.text),
            child: const Text('连接'),
          ),
        ],
      ),
    ).then((String? value) {
      if (value == null || value.isEmpty || !mounted) return;
      final String? url = WsUrl.normalize(value);
      if (url == null) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('地址格式无效')),
        );
        return;
      }
      _closeScannerThenGo(url);
    });
  }

  @override
  void dispose() {
    _scanner.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: Stack(
        children: <Widget>[
          MobileScanner(
            controller: _scanner,
            onDetect: _onDetect,
            errorBuilder: (ctx, error,_) => Center(
              child: Text(
                '相机错误: ${error.errorCode}',
                style: const TextStyle(color: Colors.white),
              ),
            ),
          ),
          Center(
            child: Container(
              width: 260,
              height: 260,
              decoration: BoxDecoration(
                border: Border.all(color: Colors.white70, width: 2),
                borderRadius: BorderRadius.circular(16),
              ),
            ),
          ),
          const Positioned(
            top: 60,
            left: 0,
            right: 0,
            child: Center(
              child: Text('扫描电脑端二维码以连接串流',
                  style: TextStyle(color: Colors.white, fontSize: 16)),
            ),
          ),
          Positioned(
            bottom: 40,
            left: 24,
            right: 24,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                if (_lastUrl != null)
                  _ActionButton(
                    icon: Icons.history,
                    label: '继续上次连接\n$_lastUrl',
                    onTap: _gotoLast,
                  ),
                const SizedBox(height: 12),
                _ActionButton(
                  icon: Icons.keyboard,
                  label: '手动输入地址',
                  onTap: _showManualInput,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ActionButton extends StatelessWidget {
  const _ActionButton({
    required this.icon,
    required this.label,
    required this.onTap,
  });
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.black54,
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: Row(
            children: <Widget>[
              Icon(icon, color: Colors.white),
              const SizedBox(width: 12),
              Expanded(
                child: Text(label,
                    style: const TextStyle(color: Colors.white, fontSize: 13)),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
