import 'package:flutter_live2d/flutter_live2d.dart';

import '../../core/config/model_config.dart';

/// 插件门面：只使用已验证存在的 setModel / startMotion / dispose / Live2dView。
/// 缺模型、缺 motion 组、插件异常一律降级（U20/U21/U22/U23），由组件层画 Transform。
class Live2DStage {
  Live2DViewController? _controller;
  ModelConfig? _current;
  bool _ready = false;
  bool active = true;

  bool get ready => _ready;
  bool get hasModel => _current != null && _current!.path.isNotEmpty;
  Live2DViewController? get controller => _controller;
  String? get degradationReason =>
      _ready ? null : '模型未就绪 / 缺 motion 组，已降级为 Transform';

  Future<void> setModel(ModelConfig cfg) async {
    if (_current?.id == cfg.id) return;
    if (cfg.path.isEmpty) {
      _ready = false;
      _current = cfg;
      return;
    }
    final Live2DViewController? old = _controller;
    final Live2DViewController next = Live2DViewController();
    _controller = next;
    _ready = false;
    try {
      await next.whenAttached.then((_) {
        final String modelDir = cfg.path.contains('/')
            ? cfg.path.substring(0, cfg.path.lastIndexOf('/'))
            : '';
        next.loadModel(modelDir: modelDir, modelFileName: cfg.path);
      });
      _ready = true;
      _current = cfg;
      old?.dispose();
    } catch (_) {
      _ready = false;
      _current = ModelConfig.fallback;
      try {
        next.dispose();
      } catch (_) {}
      _controller = null;
    }
  }

  void play(String key) {
    if (!_ready || _current == null) return;
    final String? group = _current!.motionGroups[key];
    if (group == null || group.isEmpty) return;
    try {
      _controller?.startMotion(group:group);
    } catch (_) {}
  }

  /// 只维护一个布尔，是否渲染由组件层决定（services 层不引用任何 Widget）。
  void pause() => active = false;
  void resume() => active = true;

  void dispose() {
    try {
      _controller?.dispose();
    } catch (_) {}
    _controller = null;
    _ready = false;
  }
}
