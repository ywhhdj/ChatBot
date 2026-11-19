import 'dart:async';

import 'package:flutter_live2d/flutter_live2d.dart';

import '../../core/config/load_result.dart';
import '../../core/config/model_config.dart';
import '../../core/config/model_path.dart';
import 'model_asset_installer.dart';
import 'model_entry_adapter.dart';

/// 插件门面：只使用已验证存在的 setModel / startMotion / dispose / Live2DView。
/// 缺模型、缺 motion 组、插件异常一律降级，由组件层画占位与提示。
///
/// 本轮修复的「模型无法加载显示」链路：
/// * 入口先经过 [ModelEntryAdapter]：VTube Studio 导出包 / 旧版 model.json /
///   纯 .moc3 / 带注释与 BOM 的 JSON 都转成插件能解析的标准 .model3.json；
/// * `loadModel` 返回 `Future<bool>`，**失败时返回 false 而不抛异常**，错误写在
///   `controller.value.lastError`；成功也可能是异步写 `isLoaded`。
///   现在读返回值 + 有界轮询响应式状态交叉验证，绝不把「调用发出去了」
///   或「状态还没刷新」当成加载结果；
/// * 失败回退旧 controller 时递增 [controllerRevision]，强制 Live2DView
///   换 Element —— 旧实现控制器换了、视图没换，会一直挂着已 dispose 的
///   controller，表现为黑屏 / 占位不消失；
/// * assets 内置模型先试插件原生 assets 通道；入口缺失时由适配层从
///   resources.json 生成规范化入口，走物化路径再试一次。
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
  /// 非致命提醒：入口自动发现、纹理过大、兼容入口等，加载成功后仍要展示。
  List<String> _warnings = const <String>[];

  void _emitChanged() {
    try {
      onChanged?.call();
    } catch (_) {}
  }

  static const Duration attachTimeout = Duration(milliseconds: 2500);
  static const Duration loadTimeout = Duration(seconds: 8);
  /// 插件异步写 isLoaded：最多轮询 12 × 120ms，不做无限等待。
  static const int maxStatePolls = 12;
  static const Duration statePollInterval = Duration(milliseconds: 120);

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

  /// 加载成功后仍要给用户看的提醒（4096 纹理 / 入口自动发现等）。
  List<String> get warnings => _warnings;
  String get warningText => _warnings.join(' · ');

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

    String normalized = ModelPath.normalize(cfg.path);
    String primaryDir = ModelPath.dirName(normalized);
    String primaryEntry = ModelPath.fileName(normalized);
    _warnings = const <String>[];
    bool usedMaterialized = false;

    if (cfg.isAsset) {
      final ModelInstallResult checked =
          await ModelAssetInstaller.verify(cfg);
      // 被更新的换模请求打断：旧代次直接退出，且不改 _loading
      // （新的 setModel 仍在跑，不能把它的「加载中」清掉）。
      if (gen != _generation) return;
      if (!checked.ok) {
        // 入口 JSON 不在包里（或不是标准结构）：适配层用 resources.json
        // 清单生成一份规范化入口，物化到磁盘后再交给插件解析。
        final AdaptedEntry compat =
            await ModelEntryAdapter.resolve(cfg);
        if (gen != _generation) return;
        if (compat.ok && compat.source.isNotEmpty) {
          final ModelInstallResult materialized =
              await ModelAssetInstaller.materialize(
            cfg,
            entrySource: compat.source,
            entryNameOverride: compat.fileName,
          );
          if (gen != _generation) return;
          if (materialized.ok) {
            primaryDir = ModelPath.dirName(materialized.path);
            primaryEntry = materialized.entryName.isNotEmpty
                ? materialized.entryName
                : compat.fileName;
            usedMaterialized = true;
            _warnings = <String>[...compat.warnings, ...materialized.warnings];
          } else {
            _restore(old, oldConfig, materialized.error);
            return;
          }
        } else {
          _restore(old, oldConfig, checked.error);
          return;
        }
      } else {
        primaryDir = checked.assetDir;
        // 关键：用真实入口名（大肥鱼.model3.json），不能用配置里写死的那个。
        primaryEntry = checked.entryName.isNotEmpty
            ? checked.entryName
            : primaryEntry;
        _warnings = checked.warnings;
        // 入口虽然存在但结构不标准：只登记规范化文本（零 IO），
        // 等原生通道真的失败、走物化回退时才写盘，不提前复制 4096 纹理。
        final AdaptedEntry compat =
            await ModelEntryAdapter.resolve(cfg);
        if (gen != _generation) return;
        if (compat.ok && compat.source.isNotEmpty) {
          ModelAssetInstaller.registerCompatEntry(
            cfg.path,
            compat.source,
            compat.fileName,
          );
          _warnings = <String>[..._warnings, ...compat.warnings];
        }
      }
    } else {
      // 拓宽解析：把不标准 / 残缺 / 纯 .moc3 的入口适配成标准 model3.json。
      final AdaptedEntry adapted = await ModelEntryAdapter.resolve(cfg);
      if (gen != _generation) return;
      if (!adapted.ok) {
        _restore(old, oldConfig, adapted.error);
        return;
      }
      normalized = adapted.generatedPath.isNotEmpty
          ? adapted.generatedPath
          : normalized;
      primaryDir = adapted.dir;
      primaryEntry = adapted.fileName;
      _warnings = adapted.warnings;
      // 异步预检：不在 UI isolate 上做几百次同步 stat。
      final String? local = await ModelPath.checkLocalAsync(normalized);
      if (gen != _generation) return;
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
      primaryDir,
      primaryEntry,
      attached: attached,
      cancelled: () => gen != _generation,
    );
    if (gen != _generation) {
      try {
        chosen.dispose();
      } catch (_) {}
      return;
    }

    // 原生 assets 通道被拒绝：才回退到「物化成绝对路径」再试一次。
    if (!attempt.verdict.ok && cfg.isAsset && !usedMaterialized) {
      final ModelInstallResult materialized =
          await ModelAssetInstaller.materialize(cfg);
      if (gen != _generation) {
        try {
          chosen.dispose();
        } catch (_) {}
        return;
      }
      if (materialized.ok) {
        try {
          chosen.dispose();
        } catch (_) {}
        final Live2DViewController retry = Live2DViewController();
        _controller = retry;
        _controllerRevision++;
        _reason = 'assets 通道未通过 · 正在用物化路径重试…';
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
          ModelPath.dirName(materialized.path),
          materialized.entryName.isNotEmpty
              ? materialized.entryName
              : primaryEntry,
          attached: retryAttached,
          cancelled: () => gen != _generation,
        );
        if (gen != _generation) {
          try {
            retry.dispose();
          } catch (_) {}
          return;
        }
      }
    }

    if (!attempt.verdict.ok) {
      _tryUnload(chosen);
      try {
        chosen.dispose();
      } catch (_) {}
      _restore(
        old,
        oldConfig,
        LoadResultInterpreter.failureText(
          _explainError(attempt.verdict.error),
          threw: attempt.threw,
        ),
        viewSwapped: true,
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

  /// 把插件的错误码翻译成能直接照做的排查动作。
  static String _explainError(String raw) {
    final String r = raw.isEmpty ? '原生侧未给出原因' : raw;
    if (r.contains('No assets found') || r.contains('INVALID_ARGS')) {
      return '$r · pubspec.yaml 的 flutter.assets 漏声明了模型目录或纹理子目录'
          '（assets 声明不递归，像「大肥鱼.4096/」必须单列一行）';
    }
    if (r.contains('LOAD_FAILED')) {
      return '$r · 原生 Cubism 侧拒绝了模型：路径不对 / 缺文件（尤其纹理子目录）/ '
          '.moc3 版本超出插件内置 Core 支持范围（3.0–5.3）。'
          '本 App 已自动把非标准入口转成兼容 .model3.json；若仍失败，'
          '多为 .moc3 本体缺失或纹理超出 GL_MAX_TEXTURE_SIZE，用 adb logcat 看原生日志';
    }
    if (r.contains('VIEW_NOT_ATTACHED')) {
      return '$r · GL surface 还没挂载就下发了 loadModel，点右上角刷新重试';
    }
    if (r.contains('NATIVE_ERROR')) {
      return '$r · 原生异常，常见于 4096 纹理超出 GL_MAX_TEXTURE_SIZE 或 OOM，'
          '建议改用 2048 纹理重新导出';
    }
    if (r.contains('缺少') || r.contains('只读') || r.contains('.moc3')) {
      return '$r · 解析适配层已给出具体缺失项，补齐后点「重新自检模型资源」';
    }
    return r;
  }

  /// 1.0.2 起插件提供 `unloadModel()`：失败时把原生侧已分配的资源释放掉。
  /// 用 dynamic 调用，老版本没有这个方法也不会编译失败。
  static void _tryUnload(Live2DViewController c) {
    try {
      (c as dynamic).unloadModel();
    } catch (_) {}
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
  /// 状态是异步写入的，先有界轮询再下结论。
  Future<_LoadAttempt> _attempt(
    Live2DViewController c,
    String dir,
    String file, {
    required bool attached,
    bool Function()? cancelled,
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
      LoadVerdict verdict = const LoadVerdict(false, '未确认');
      for (int i = 0; i <= maxStatePolls; i++) {
        if (cancelled?.call() == true) {
          return _LoadAttempt(
            const LoadVerdict(false, '换模请求打断'),
            threw: true,
          );
        }
        final bool? loaded = _stateIsLoaded(c);
        final String err = _stateError(c);
        verdict = LoadResultInterpreter.interpret(
          futureValue: awaited,
          stateIsLoaded: loaded,
          stateError: err,
        );
        if (!LoadResultInterpreter.needsPoll(
          futureValue: awaited,
          stateIsLoaded: loaded,
          stateError: err,
        )) {
          break;
        }
        if (i < maxStatePolls) {
          await Future<void>.delayed(statePollInterval);
        }
      }
      // 没等到 attach：只有「原生没明确确认渲染」时才否决。
      // 插件返回 true 且 isLoaded=true 时，超时不该把已画出来的模型判成失败。
      if (!attached &&
          verdict.ok &&
          !(awaited == true && _stateIsLoaded(c) == true)) {
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
  /// [viewSwapped] = 本代次已经创建并挂过新 controller：回退时必须换 Element，
  /// 否则 Live2DView 仍持有被 dispose 的 controller，表现为黑屏/占位不消失。
  void _restore(
    Live2DViewController? old,
    ModelConfig? oldConfig,
    String reason, {
    bool viewSwapped = false,
  }) {
    _controller = old;
    _current = oldConfig;
    _ready = old != null && _stateIsLoaded(old) == true;
    _loading = false;
    _reason = reason;
    if (viewSwapped) _controllerRevision++;
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
    _warnings = const <String>[];
  }
}

class _LoadAttempt {
  const _LoadAttempt(this.verdict, {this.threw = false});

  final LoadVerdict verdict;
  /// 调用本身抛了异常（与「返回 false」区分，后者才值得换路径重试）。
  final bool threw;
}
