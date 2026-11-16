/// 命名路由去重守卫（纯 Dart，便于单元测试）。
///
/// 「刷新 / 设定 / 历史」按钮若在重建期间被连点，或同一次点击被两棵子树
/// 各处理一次，就会连续 push 出多层同名页面；返回时用户看到的是
/// 「页面一闪而过」。这里用一个有界集合保证同名路由同时只存在一条。
class RouteGuard {
  RouteGuard._();

  static final Set<String> _active = <String>{};

  /// true = 允许进入（此前栈中没有同名路由）；false = 已存在，忽略本次点击。
  static bool tryEnter(String name) => name.isEmpty ? false : _active.add(name);

  static void leave(String name) => _active.remove(name);

  static bool isActive(String name) => _active.contains(name);

  static int get activeCount => _active.length;

  /// 仅供测试重置。
  static void reset() => _active.clear();
}
