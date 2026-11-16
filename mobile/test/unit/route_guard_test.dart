import 'package:ar_live2d_agent/core/config/route_guard.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  setUp(RouteGuard.reset);
  tearDown(RouteGuard.reset);

  test('同名路由同时只允许进入一次', () {
    expect(RouteGuard.tryEnter('/settings'), isTrue);
    expect(RouteGuard.tryEnter('/settings'), isFalse);
    expect(RouteGuard.isActive('/settings'), isTrue);
    expect(RouteGuard.activeCount, 1);
  });

  test('leave 之后可以再次进入', () {
    expect(RouteGuard.tryEnter('/settings'), isTrue);
    RouteGuard.leave('/settings');
    expect(RouteGuard.isActive('/settings'), isFalse);
    expect(RouteGuard.tryEnter('/settings'), isTrue);
  });

  test('不同路由互不干扰，空名字被忽略', () {
    expect(RouteGuard.tryEnter('/settings'), isTrue);
    expect(RouteGuard.tryEnter('/history'), isTrue);
    expect(RouteGuard.tryEnter(''), isFalse);
    expect(RouteGuard.activeCount, 2);
  });
}
