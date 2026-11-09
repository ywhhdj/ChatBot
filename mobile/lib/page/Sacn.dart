import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'ARLive2D.dart';

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
    final prefs = await SharedPreferences.getInstance();
    final url = prefs.getString('last_ws_url');
    if (url != null && mounted) {
      setState(() => _lastUrl = url);
    }
  }

  Future<void> _onDetect(BarcodeCapture capture) async {
    if (_handled) return;
    final raw = capture.barcodes.firstOrNull?.rawValue;
    if (raw == null) return;

    final url = _normalizeWsUrl(raw);
    if (url == null) return;

    _handled = true;
    await _scanner.stop();

    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('last_ws_url', url);

    if (!mounted) return;
    _gotoArPage(url);
  }

  /// 允许扫码内容是以下几种形式：
  /// 1. ws://192.168.1.100:8765/ws
  /// 2. http(s)://192.168.1.100:8765  → 自动转为 ws://.../ws
  /// 3. 192.168.1.100:8765           → 补全 ws:// 并加 /ws
  String? _normalizeWsUrl(String input) {
    final trimmed = input.trim();
    if (trimmed.isEmpty) return null;

    if (trimmed.startsWith('ws://') || trimmed.startsWith('wss://')) {
      return trimmed;
    }
    if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
      final uri = Uri.parse(trimmed);
      return 'ws://${uri.host}:${uri.hasPort ? uri.port : 8765}/ws';
    }
    // 裸 host:port
    final parts = trimmed.split(':');
    if (parts.length == 2 && int.tryParse(parts[1]) != null) {
      return 'ws://${parts[0]}:${parts[1]}/ws';
    }
    return null;
  }

  void _gotoArPage(String url) {
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => ArLive2DPage(wsUrl: url)),
    );
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
        children: [
          MobileScanner(
            controller: _scanner,
            onDetect: _onDetect,
            errorBuilder: (ctx, error) => Center(
              child: Text('相机错误: ${error.errorCode}',
                  style: const TextStyle(color: Colors.white)),
            ),
          ),

          // 扫描框
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

          // 顶部提示
          Positioned(
            top: 60,
            left: 0,
            right: 0,
            child: const Center(
              child: Text(
                '扫描电脑端二维码以连接串流',
                style: TextStyle(color: Colors.white, fontSize: 16),
              ),
            ),
          ),

          // 底部：上次连接 & 手动输入
          Positioned(
            bottom: 40,
            left: 24,
            right: 24,
            child: Column(
              children: [
                if (_lastUrl != null)
                  _ActionButton(
                    icon: Icons.history,
                    label: '继续上次连接\n$_lastUrl',
                    onTap: () => _gotoArPage(_lastUrl!),
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

  Future<void> _showManualInput() async {
    final controller = TextEditingController();
    final url = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('输入串流地址'),
        content: TextField(
          controller: controller,
          decoration: const InputDecoration(
            hintText: 'ws://192.168.1.100:8765/ws',
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('取消')),
          TextButton(
            onPressed: () => Navigator.pop(ctx, controller.text),
            child: const Text('连接'),
          ),
        ],
      ),
    );
    if (url == null || url.isEmpty) return;
    final normalized = _normalizeWsUrl(url);
    if (normalized == null) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('地址格式无效')),
      );
      return;
    }
    _gotoArPage(normalized);
  }
}

class _ActionButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  const _ActionButton({
    required this.icon,
    required this.label,
    required this.onTap,
  });

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
            children: [
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