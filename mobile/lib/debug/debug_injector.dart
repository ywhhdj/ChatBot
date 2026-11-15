import '../app/stage_session.dart';

/// 模拟注入：只在 debug/ 内，和真实 WS 源互斥（U59）。
class DebugInjector {
  const DebugInjector(this.session);

  final StageSession session;

  static const List<String> actions = <String>[
    'fling_out', 'peek_back', 'return_idle', 'jump_out',
    'turn_left', 'turn_right', 'asr', 'delta',
  ];

  void inject(String action) {
    session.inject(action);
  }

  void setMock(bool value) {
    session.mockMode = value;
    DebugInjectorProxy.mock = value;
  }
}

/// 给 HUD 显示的轻量镜像，避免 debug 层反向持有业务对象。
class DebugInjectorProxy {
  static bool mock = false;
}
