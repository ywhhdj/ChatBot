import 'dart:async';

import 'package:flutter_live2d/flutter_live2d.dart';

import '../../core/config/model_config.dart';
import '../../core/config/model_path.dart';

/// 插件门面：只使用已验证存在的 setModel / startMotion / dispose / Live2DView。
/// 缺模型、缺 motion 组、插件异常一律降级（U20-U23），由组件层画 Transform。
///
/// 关键修复（模型不加载的根因）：
/// * `whenAttached` **不能无限等待** —— 组件层只在 ready 后才显示 Live2DView，
///   而 ready 又要等 attach，构成死锁，会连带把整个 StageSession.start() 卡住。
///   这里改成有上限的等待，超时也继续尝试 loadModel，绝不阻塞启动流程；
/// * 组件层现在把 Live2DView 常驻在树里（未就绪时用占位盖住），attach 才有机会完成；
/// * 加载失败保留旧 controller 与**旧 config**，原来把 `_current` 改成新 cfg 会让
///   同 id 的后续重试被 `!force` 早退掉，变成「永远加载不了」；
/// * 绝对路径先做文件存在性预检，缺文件给明确原因而不是让插件静默失败。
class Live2DStage {
  Live2DStage({this.onChanged});

  /// controller / ready / 降级原因变化时通知装配层刷新 UI。
  /// 关键是「创建 controller 后立刻通知」：组件层这才会把 Live2DView 挂进树，
  /// `whenAttached` 才有机会在超时前完成（否则又会退化成先 loadModel 后挂载）。
  final void Function()? onChanged;

  Live2DViewController? _controller;
  ModelConfig? _current;
  bool _ready = false;
  bool active = true;
  String? _reason;
  int _generation = 0;

  void _emitChanged() {
    try {
      onChanged?.call();
    } catch (_) {}
  }

  /// attach 最多等这么久，超时仍继续 loadModel（插件内部通常会排队到视图挂载后）。
  static const Duration attachTimeout = Duration(milliseconds: 2500);

  bool get ready => _ready;
  bool get hasModel => _current != null && _current!.path.isNotEmpty;
  Live2DViewController? get controller => _controller;
  String? get degradationReason => _reason;
  ModelConfig? get current => _current;

  Future<void> setModel(ModelConfig cfg, {bool force = false}) async {
    if (_current?.id == cfg.id && !force) return;
    final int gen = ++_generation;
    final Live2DViewController? old = _controller;
    final ModelConfig? oldConfig = _current;

    if (cfg.path.isEmpty) {
      try {
        old?.dispose();
      } catch (_) {}
      _controller = null;
      _current = cfg;
      _ready = false;
      _reason = '未选择模型 · 请到「设定 → 模型」选模型或选择目录';
      _emitChanged();
      return;
    }

    // 预检：content:// / URI 无法被原生文件 IO 直接读取；绝对路径必须存在。
    final String? precheck = ModelPath.validate(cfg.path);
    if (precheck != null) {
      _controller = old;
      _current = oldConfig;
      _ready = old != null;
      _reason = precheck;
      _emitChanged();
      return;
    }

    final Live2DViewController next = Live2DViewController();
    _controller = next;
    _current = cfg;
    _ready = false;
    _reason = '模型加载中…';
    // 先让 UI 挂上 Live2DView，whenAttached 才能完成，避免死锁。
    _emitChanged();
    try {
      // Future.value 兼容 whenAttached 是 Future / FutureOr / 同步值的各种插件版本；
      // 任何异常或超时都不再阻塞 start()，交给组件层的常驻 Live2DView 完成 attach。
      await Future<dynamic>.value(next.whenAttached).timeout(attachTimeout);
    } catch (_) {
      // 超时 / 插件不支持等待：继续尝试 loadModel，不视为失败。
    }
    if (gen != _generation) {
      try {
        next.dispose();
      } catch (_) {}
      return;
    }

    try {
      // assets 内置与用户自选目录的绝对路径都拆成 dirName + fileName，
      // 不能把完整路径再塞进 modelFileName（插件会拼成重复路径）。
      next.loadModel(modelDir: cfg.dirName, modelFileName: cfg.fileName);
      _ready = true;
      _reason = null;
      _emitChanged();
      try {
        old?.dispose();
      } catch (_) {}
    } catch (e) {
      try {
        next.dispose();
      } catch (_) {}
      if (gen != _generation) return;
      // 保留上次可用 controller **和它的 config**，否则同 id 重试会被早退吞掉。
      _controller = old;
      _current = oldConfig;
      _ready = old != null;
      _reason = old == null
          ? '模型加载失败，请重试：${e.runtimeType}（检查模型目录与文件名）'
          : '模型加载失败，请重试（已保留上一个可用模型）';
      _emitChanged();
    }
  }

  void play(String key) {
    if (!_ready || _current == null) return;
    final String? group = _current!.motionGroups[key];
    if (group == null || group.isEmpty) return;
    try {
      _controller?.startMotion(group: group);
    } catch (_) {}
  }

  /// 只维护一个布尔，是否渲染由组件层决定（services 层不引用任何 Widget）。
  void pause() => active = false;
  void resume() => active = true;

  void dispose() {
    _generation++;
    try {
      _controller?.dispose();
    } catch (_) {}
    _controller = null;
    _current = null;
    _ready = false;
    _reason = null;
  }
}
