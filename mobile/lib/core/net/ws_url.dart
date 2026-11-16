import 'dart:convert';

import '../config/app_config.dart';
import 'device_identity.dart';

/// 扫码 / 手输地址解析结果：归一化的 ws 地址 + 可选的配对 uid。
class WsEndpoint {
  const WsEndpoint(this.url, {this.uid = ''});

  final String url;
  final String uid;

  bool get hasUid => uid.isNotEmpty;
}

/// 地址归一化：统一产出 ws(s)://host:port/ 。
/// 支持三种二维码内容：
///   1. 裸地址 `192.168.1.10:8000`
///   2. 带配对 uid 的地址 `ws://192.168.1.10:8000/?uid=desktop-xxxx`
///   3. JSON `{"url":"ws://...","uid":"desktop-xxxx"}`
/// 与电脑端使用同一 uid 后，服务端的 send_to_device(uid, device) 才能精确命中。
class WsUrl {
  WsUrl._();

  static WsEndpoint? parse(String raw) {
    String t = raw.trim();
    if (t.isEmpty) return null;
    String uid = '';

    if (t.startsWith('{')) {
      try {
        final dynamic decoded = jsonDecode(t);
        if (decoded is Map) {
          final Map<String, dynamic> m = Map<String, dynamic>.from(decoded);
          uid = (m['uid'] ?? '').toString();
          t = (m['url'] ?? m['ws'] ?? m['host'] ?? '').toString().trim();
        }
      } catch (_) {
        return null;
      }
      if (t.isEmpty) return null;
    }

    // 二维码里 ?uid= 与地址本体分离，避免把 query 拼进 ws 路径。
    final int q = t.indexOf('?');
    if (q >= 0) {
      final String query = t.substring(q + 1);
      t = t.substring(0, q);
      for (final String part in query.split('&')) {
        final int eq = part.indexOf('=');
        if (eq > 0 && part.substring(0, eq) == 'uid') {
          uid = Uri.decodeComponent(part.substring(eq + 1));
        }
      }
    }
    if (uid.isNotEmpty && !DeviceIdentity.isValid(uid)) uid = '';

    final String? url = _normalizePlain(t);
    if (url == null) return null;
    return WsEndpoint(url, uid: uid);
  }

  /// 旧接口：只取归一化地址（保持既有测试与调用点不变）。
  static String? normalize(String raw) => parse(raw)?.url;

  static String? _normalizePlain(String raw) {
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
      final Uri u;
      try {
        u = Uri.parse(t);
      } catch (_) {
        return null;
      }
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
