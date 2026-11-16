import 'dart:async';

import 'package:flutter_live2d/flutter_live2d.dart';

import '../../core/config/load_result.dart';
import '../../core/config/model_config.dart';
import '../../core/config/model_path.dart';
import 'model_asset_installer.dart';

/// 插件门面：只使用已验证存在的 setModel / startMotion / dispose / Live2DView。
/// 缺模型、缺 motion 组、插件异常一律降级，由组件层画占位与提示。
///
/// 「检测通过、显示已就绪、占位消失、却看不到模型」的根因与修复：
/// * `loadModel` 返回 `Future<bool>`，**失败时返回 false 而不抛异常**，错误写在
///   `controller.value.lastError`（LOAD_FAILED）。旧实现只 await 了 Future 就
///   置 `_ready = true`，等于把「调用发出去了」当成「模型画出来了」；
/// * 现在读取返回值 + 响应式状态交叉验证，只有原生侧真的确认加载才置 ready；
/// * 文件存在性自检（入口 JSON / FileReferences）只能证明文件在，不能证明
///   `.moc3` 能被 Cubism Core 解析，这两件事在 UI 上明确区分；
/// * assets 内置模型先试物化后的绝对路径，被原生侧拒绝时自动用 pubspec 声明的
///   assets 目录再试一次（插件自己会把 assets 解压到 cache）；
/// * `whenAttached` 超时不再静默当成成功，会走失败分支给出原因。
class Live2DStage {
  Live2DStage({this.onChanged});

  /// controller / ready / 降级原因变化时通知装配层刷新 UI。
  final void Function()? onChanged;

  Live2DViewController? _controller;
  ModelConfig? _current;
  bool _ready = false;
  bool _loading = false;
  bool active = true;
  String? _reason;
  int _generation = 0;
  int _controllerRevision = 0;

  void _emitChanged() {
    try {
      onChanged?.call();
    } catch (_) {}
  }

  static const Duration attachTimeout = Duration(milliseconds: 2500);
  static const Duration loadTimeout = Duration(seconds: 8);

  bool get ready => _ready;
  bool get loading => _loading;
  bool get hasModel => _current != null && _current!.path.isNotEmpty;
  Live2DViewController? get controller => _controller;
  String? get degradationReason => _reason;
  ModelConfig? get current => _current;
  int get controllerRevision => _controllerRevision;

  String get statusText {
    if (_loading) return '模型加载中…';
    if (_ready) return '模型已就绪';
    return '模型未加载';
  }

  /// 未就绪时给出具体原因，供占位层与设定页展示。
  String get detailText => _reason ?? statusText;

  Future<void> setModel(ModelConfig cfg, {bool force = false}) async {
    if (_current?.id == cfg.id && !force && _ready) return;
    final int gen = ++_generation;
    final Live2DViewController? old = _controller;
    final ModelConfig? oldConfig = _current;
    _loading = true;

    if (cfg.path.isEmpty) {
      _loading = false;
      try {
        old?.dispose();
      } catch (_) {}
      _controller = null;
      _current = cfg;
      _ready = false;
      _controllerRevision++;
      _reason = '未选择模型 · 请到「设定 → 模型」选模型或选择目录';
      _emitChanged();
      return;
    }

    final String? precheck = ModelPath.validate(cfg.path);
    if (precheck != null) {
      _restore(old, oldConfig, precheck);
      return;
    }

    // assets 内置：物化到应用文档目录，返回真实绝对路径；
    // 用户目录：核对入口 JSON 的依赖文件是否齐全。
    String realPath = ModelPath.normalize(cfg.path);
    if (cfg.isAsset) {
      final ModelInstallResult installed =
          await ModelAssetInstaller.materialize(cfg);
      // 被更新的换模请求打断：旧代次直接退出，且不改 _loading
      // （新的 setModel 仍在跑，不能把它的「加载中」清掉）。
      if (gen != _generation) return;
      if (!installed.ok) {
        _restore(old, oldConfig, installed.error);
        return;
      }
      realPath = installed.path;
    } else {
      final String? local = ModelPath.checkLocal(realPath);
      if (local != null) {
        _restore(old, oldConfig, local);
        return;
      }
    }

    Live2DViewController chosen = Live2DViewController();
    _controller = chosen;
    _current = cfg;
    _ready = false;
    _controllerRevision++;
    _reason = '模型加载中…';
    // 先让 UI 挂上 Live2DView，whenAttached 才能完成，避免死锁。
    _emitChanged();
    final bool attached = await _waitAttached(chosen);
    if (gen != _generation) {
      try {
        chosen.dispose();
      } catch (_) {}
      return;
    }

    _LoadAttempt attempt = await _attempt(
      chosen,
      ModelPath.dirName(realPath),
      ModelPath.fileName(realPath),
      attached: attached,
    );
    if (gen != _generation) {
      try {
        chosen.dispose();
      } catch (_) {}
      return;
    }

    // 内置模型：物化目录被原生侧拒绝时，用插件原生支持的 assets 目录再试一次。
    // 插件会自行把 pubspec 声明的 assets 解压到 cache，不一定认我们复制的目录。
    if (!attempt.verdict.ok && cfg.isAsset && !attempt.threw) {
      try {
        chosen.dispose();
      } catch (_) {}
      final Live2DViewController retry = Live2DViewController();
      _controller = retry;
      _controllerRevision++;
      _reason = '物化路径未通过 · 正在用 assets 目录重试…';
      _emitChanged();
      final bool retryAttached = await _waitAttached(retry);
      if (gen != _generation) {
        try {
          retry.dispose();
        } catch (_) {}
        return;
      }
      chosen = retry;
      attempt = await _attempt(
        retry,
        ModelPath.dirName(cfg.path),
        ModelPath.fileName(cfg.path),
        attached: retryAttached,
      );
      if (gen != _generation) {
        try {
          retry.dispose();
        } catch (_) {}
        return;
      }
    }

    if (!attempt.verdict.ok) {
      try {
        chosen.dispose();
      } catch (_) {}
      _restore(
        old,
        oldConfig,
        LoadResultInterpreter.failureText(
          attempt.verdict.error,
          threw: attempt.threw,
        ),
      );
      return;
    }

    _controller = chosen;
    _current = cfg;
    _ready = true;
    _reason = null;
    _loading = false;
    _emitChanged();
    if (!identical(old, chosen)) {
      try {
        old?.dispose();
      } catch (_) {}
    }
  }

  /// 等原生 GL surface 挂载；超时返回 false，由调用方明确记为「未确认」，
  /// 绝不把超时静默当作加载成功。
  Future<bool> _waitAttached(Live2DViewController c) async {
    try {
      await Future<dynamic>.value(c.whenAttached).timeout(attachTimeout);
      return true;
    } catch (_) {
      return false;
    }
  }

  /// 真正下发 loadModel，并按「返回值 + controller 响应式状态」判定成败。
  Future<_LoadAttempt> _attempt(
    Live2DViewController c,
    String dir,
    String file, {
    required bool attached,
  }) async {
    try {
      // 借 dynamic receiver 调用：不同插件版本返回 Future<bool> / Future / void，
      // 静态类型接 void 结果会编译报错；dynamic 调用可统一等待。
      final dynamic plugin = c;
      final dynamic result = plugin.loadModel(
        modelDir: dir,
        modelFileName: file,
      );
      final dynamic awaited =
          await Future<dynamic>.value(result).timeout(loadTimeout);
      final bool? stateLoaded = _stateIsLoaded(c);
      final String stateError = _stateError(c);
      LoadVerdict verdict = LoadResultInterpreter.interpret(
        futureValue: awaited,
        stateIsLoaded: stateLoaded,
        stateError: stateError,
      );
      // 没等到 attach：即使插件返回了 true，也不能确认模型画在 surface 上。
      if (!attached && verdict.ok) {
        verdict = const LoadVerdict(false, '视图未挂载（whenAttached 超时）');
      }
      return _LoadAttempt(verdict);
    } catch (e) {
      final String stateError = _stateError(c);
      return _LoadAttempt(
        LoadVerdict(false, stateError.isNotEmpty ? stateError : '${e.runtimeType}'),
        threw: true,
      );
    }
  }

  /// controller 是 ValueNotifier<Live2DViewState>：用 dynamic 读字段，
  /// 字段名若随插件版本变化也不会编译失败，运行时异常一律吞掉返回空。
  static dynamic _stateOf(Live2DViewController c) {
    try {
      return (c as dynamic).value;
    } catch (_) {
      return null;
    }
  }

  static bool? _stateIsLoaded(Live2DViewController c) {
    final dynamic s = _stateOf(c);
    if (s == null) return null;
    try {
      final dynamic v = s.isLoaded;
      return v is bool ? v : null;
    } catch (_) {
      return null;
    }
  }

  static String _stateError(Live2DViewController c) {
    final dynamic s = _stateOf(c);
    if (s == null) return '';
    String code = '';
    String message = '';
    try {
      final dynamic e = s.lastError;
      if (e == null) return '';
      try {
        code = (e.code ?? '').toString();
      } catch (_) {}
      try {
        message = (e.message ?? '').toString();
      } catch (_) {}
    } catch (_) {
      return '';
    }
    if (code.isEmpty) return message;
    if (message.isEmpty || message == code) return code;
    return '$code · $message';
  }

  /// 保留上一次可用 controller 与它的 config，避免同 id 重试被早退吞掉。
  /// 旧 controller 只有在它自己确实加载过时才算可用，不再无条件认为「就绪」。
  void _restore(
    Live2DViewController? old,
    ModelConfig? oldConfig,
    String reason,
  ) {
    _controller = old;
    _current = oldConfig;
    _ready = old != null && _stateIsLoaded(old) == true;
    _loading = false;
    _reason = reason;
    _emitChanged();
  }

  /// 当前模型配置里登记的动作组（设定页快捷试播用）。
  Set<String> get availableGroups =>
      _current?.motionGroups.values.toSet() ?? <String>{};

  /// 按 Cubism 动作组名点播，返回是否真的下发给插件。
  bool playGroup(String group) {
    if (!_ready || group.isEmpty || _controller == null) return false;
    try {
      _controller!.startMotion(group: group);
      return true;
    } catch (_) {
      return false;
    }
  }

  /// 兼容配置 key（idle → Idle）与直接动作组名（Idle）。
  void play(String key) {
    if (!_ready || _current == null || key.isEmpty) return;
    final String? mapped = _current!.motionGroups[key];
    final String group = (mapped != null && mapped.isNotEmpty) ? mapped : key;
    try {
      _controller?.startMotion(group: group);
    } catch (_) {}
  }

  /// 只维护一个布尔，是否渲染由组件层决定（services 层不引用任何 Widget）。
  void pause() => active = false;
  void resume() => active = true;

  void dispose() {
    _generation++;
    _loading = false;
    _controllerRevision++;
    try {
      _controller?.dispose();
    } catch (_) {}
    _controller = null;
    _current = null;
    _ready = false;
    _reason = null;
  }
}

class _LoadAttempt {
  const _LoadAttempt(this.verdict, {this.threw = false});

  final LoadVerdict verdict;
  /// 调用本身抛了异常（与「返回 false」区分，后者才值得换路径重试）。
  final bool threw;
}
