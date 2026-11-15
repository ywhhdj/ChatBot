import 'package:flutter_test/flutter_test.dart';
import 'package:ar_live2d_agent/core/net/ws_url.dart';

void main() {
  group('WsUrl.normalize', () {
    test('裸 host:port 补全 ws 与根路径', () {
      expect(WsUrl.normalize('192.168.1.10:8000'), 'ws://192.168.1.10:8000/');
    });
    test('http(s) 转 ws(s)，丢弃 /ws 旧路径', () {
      expect(WsUrl.normalize('http://192.168.1.10:8000/ws'),
          'ws://192.168.1.10:8000/');
      expect(WsUrl.normalize('https://example.com:9443'),
          'wss://example.com:9443/');
    });
    test('已是 ws 地址时保持根路径', () {
      expect(WsUrl.normalize('ws://10.0.0.2:8765/'), 'ws://10.0.0.2:8765/');
    });
    test('非法输入返回 null', () {
      expect(WsUrl.normalize(''), isNull);
      expect(WsUrl.normalize('192.168.1.10:abc'), isNull);
    });
  });
}
