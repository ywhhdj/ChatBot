import '../config/app_config.dart';

/// 扫码 / 手输地址归一化：统一产出 ws(s)://host:port/ 。
/// 旧实现的 /ws 与 8765 端口均已作废（见 docs/contracts/device_events.md）。
class WsUrl {
  WsUrl._();

  static String? normalize(String raw) {
    final String t = raw.trim();
    if (t.isEmpty) return null;

    String host = '';
    int port = AppConfig.defaultPort;
    String scheme = 'ws';

    final bool hasScheme = t.startsWith('ws://') ||
        t.startsWith('wss://') ||
        t.startsWith('http://') ||
        t.startsWith('https://');
    if (hasScheme) {
      final Uri u = Uri.parse(t);
      if (u.host.isEmpty) return null;
      host = u.host;
      if (u.hasPort) port = u.port;
      scheme = (u.scheme == 'wss' || u.scheme == 'https') ? 'wss' : 'ws';
    } else {
      final int idx = t.lastIndexOf(':');
      if (idx > 0 && idx < t.length - 1) {
        host = t.substring(0, idx);
        final int? p = int.tryParse(t.substring(idx + 1));
        if (p == null) return null;
        port = p;
      } else {
        host = t;
      }
    }
    if (host.isEmpty) return null;
    return '$scheme://$host:$port/';
  }
}
