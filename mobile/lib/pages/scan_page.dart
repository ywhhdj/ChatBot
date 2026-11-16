import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../app/gal_palette.dart';
import '../app/routes.dart';
import '../core/config/app_config.dart';
import '../core/net/ws_url.dart';
import '../services/storage/prefs.dart';

/// 扫码入口：右上角「跳过」进入离线单机（模型可用、无法连接），
/// 之后在「设定 → 连接」或「手动输入地址」页填地址即可联网；不用任何弹窗。
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
    if (url != null && url.isNotEmpty && mounted) {
      setState(() => _lastUrl = url);
    }
  }

  Future<void> _onDetect(BarcodeCapture capture) async {
    if (_handled || capture.barcodes.isEmpty) return;
    final String? raw = capture.barcodes.first.rawValue;
    final WsEndpoint? endpoint = raw == null ? null : WsUrl.parse(raw);
    if (endpoint == null) return;
    _handled = true;
    await _closeScannerThenGo(endpoint);
  }

  /// 三条跳转路径统一先停相机再走，避免相机占用导致舞台页初始化失败。
  Future<void> _closeScannerThenGo(WsEndpoint endpoint) async {
    try {
      await _scanner.stop();
    } catch (_) {}
    if (endpoint.url.isNotEmpty) {
      await Prefs.setLastWsUrl(endpoint.url);
    }
    if (!mounted) return;
    AppConfig.wsUrl = endpoint.url;
    await Navigator.of(context)
        .pushReplacementNamed(AppRoutes.stage, arguments: endpoint);
  }

  void _gotoLast() {
    final String url = _lastUrl ?? '';
    if (url.isEmpty) return;
    final WsEndpoint? endpoint = WsUrl.parse(url);
    if (endpoint == null) return;
    _closeScannerThenGo(endpoint);
  }

  void _skip() => _closeScannerThenGo(const WsEndpoint(''));

  /// 手动输入地址：全屏新页面，不再弹 AlertDialog。
  Future<void> _gotoConnect() async {
    try {
      await _scanner.stop();
    } catch (_) {}
    if (!mounted) return;
    await AppRoutes.pushOnce(context, AppRoutes.connect);
    // 从连接页回来后相机重新启动，保证扫码仍可用。
    if (mounted) {
      try {
        await _scanner.start();
      } catch (_) {}
    }
  }

  @override
  void dispose() {
    _scanner.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: GalPalette.of(context).scaffold,
      body: Stack(
        children: <Widget>[
          MobileScanner(
            controller: _scanner,
            onDetect: _onDetect,
            errorBuilder: (ctx, error, _) => Center(
              child: Text(
                '相机错误：${error.errorCode} · 可点右上角「跳过」或手动输入',
                style: TextStyle(
                  color: GalPalette.of(context).accent,
                  fontSize: 13,
                ),
                textAlign: TextAlign.center,
              ),
            ),
          ),
          Center(
            child: Container(
              width: 260,
              height: 260,
              decoration: BoxDecoration(
                border: Border.all(
                  color: GalPalette.of(context).scanFrame,
                  width: 2,
                ),
                borderRadius: BorderRadius.circular(16),
              ),
            ),
          ),
          Positioned(
            top: 96,
            left: 0,
            right: 0,
            child: Center(
              child: Text(
                '扫描电脑端二维码以连接串流',
                style: TextStyle(
                  color: GalPalette.of(context).text,
                  fontSize: 16,
                  letterSpacing: 1.2,
                ),
              ),
            ),
          ),
          Positioned(
            top: 126,
            left: 0,
            right: 0,
            child: Center(
              child: Text(
                '跳过扫码可离线单机演出（模型可用，系统识别可用）',
                style: TextStyle(
                  color: GalPalette.of(context).textDim,
                  fontSize: 11,
                ),
              ),
            ),
          ),
          // 右上角跳过：离线入口。
          Positioned(
            top: 0,
            right: 0,
            child: SafeArea(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(
                    foregroundColor: GalPalette.of(context).accent,
                    backgroundColor: GalPalette.of(context).dialog
                        .withValues(alpha: .88),
                    side: BorderSide(color: GalPalette.of(context).border),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(20),
                    ),
                  ),
                  onPressed: _skip,
                  label: const Text('跳过', style: TextStyle(fontSize: 12)),
                ),
              ),
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
                  onTap: _gotoConnect,
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
      color: GalPalette.of(context).dialog.withValues(alpha: .9),
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: GalPalette.of(context).borderSoft),
          ),
          child: Row(
            children: <Widget>[
              Icon(icon, color: GalPalette.of(context).accent),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  label,
                  style: TextStyle(
                    color: GalPalette.of(context).text,
                    fontSize: 13,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
