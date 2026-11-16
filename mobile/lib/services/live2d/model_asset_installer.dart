import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';

import '../../core/config/model_config.dart';
import '../../core/config/model_path.dart';

/// 内置模型安装结果。
class ModelInstallResult {
  const ModelInstallResult(
    this.path, {
    this.error = '',
    this.missing = const <String>[],
  });

  /// 可直接交给 Live2D 插件的绝对路径；失败时为空串。
  final String path;
  final String error;
  final List<String> missing;

  bool get ok => error.isEmpty && path.isNotEmpty;
  bool get isAssetFallback => path.isEmpty && error.isEmpty;
}

/// 把 `assets/` 里的 Live2D 模型物化到应用文档目录，再交给插件加载。
///
/// 修复「模型已就绪却不显示」的第二道闸：
/// * Flutter 的 asset 不是文件系统路径，`loadModel(modelDir: 'assets/...')`
///   在原生侧通常读不到文件，插件静默失败，Dart 侧却已经把 ready 置成 true；
/// * 这里按入口 JSON 的 FileReferences 把 .moc3 / 纹理 / 动作 / 表情
///   逐个复制到 `${应用文档目录}/live2d/<id>/`，返回真实绝对路径；
/// * 缺任何一个引用文件都直接报出文件名清单，不再假装加载成功；
/// * 成功结果按入口路径缓存，重启只做一次存在性检查，避免反复解码大纹理。
class ModelAssetInstaller {
  ModelAssetInstaller._();

  static const String _markerName = '.installed.json';
  static const int _installVersion = 1;
  static const int _maxRefs = 512;

  static final Map<String, ModelInstallResult> _cache =
      <String, ModelInstallResult>{};

  /// 最近一次自检结果：设置页「存储与维护」用它展示缺失清单。
  static ModelInstallResult? lastResult;

  static void invalidate([String? assetPath]) {
    if (assetPath == null) {
      _cache.clear();
      lastResult = null;
    } else {
      _cache.remove(assetPath);
    }
  }

  /// 纯函数：抽出入口 JSON 引用的资源文件。
  static List<String> referencesFrom(String source) =>
      ModelPath.parseReferences(source);

  /// 资源 key：入口所在 asset 目录 + 相对引用，规范化后不允许越界。
  ///
  /// 不能用 `Uri(path:).normalizePath().path`：Uri.path 会把中文文件名
  /// percent-encode（例如 `Exp3/加载.exp3.json` → `Exp3/%E5%8A%A0...`），
  /// 而 rootBundle.load 要的是原始 asset key，仓库里恰好有中文动作 / 表情。
  /// 这里做纯字符串规范化，保留 Unicode 原样。
  static String assetKey(String assetDir, String ref) {
    final String rel = ModelPath.normalize(ref);
    final String joined = assetDir.isEmpty ? rel : '$assetDir/$rel';
    final List<String> parts = <String>[];
    for (final String part in joined.split('/')) {
      if (part.isEmpty || part == '.') continue;
      if (part == '..') {
        if (parts.isNotEmpty) parts.removeLast();
      } else {
        parts.add(part);
      }
    }
    return parts.join('/');
  }

  static bool _escapes(String ref) {
    final String r = ModelPath.normalize(ref);
    return r.startsWith('../') || r.contains('/../') || r == '..';
  }

  static ModelInstallResult _fail(
    String message, [
    List<String> missing = const <String>[],
  ]) {
    final ModelInstallResult result = ModelInstallResult(
      '',
      error: message,
      missing: missing,
    );
    lastResult = result;
    return result;
  }

  /// 把内置模型装到磁盘；用户自选目录的绝对路径原样返回（由 ModelPath 校验）。
  static Future<ModelInstallResult> materialize(
    ModelConfig cfg, {
    AssetBundle? bundle,
  }) async {
    final String assetPath = ModelPath.normalize(cfg.path);
    if (!assetPath.startsWith('assets/')) {
      return ModelInstallResult(assetPath);
    }

    final ModelInstallResult? cached = _cache[assetPath];
    if (cached != null && cached.ok && File(cached.path).existsSync()) {
      lastResult = cached;
      return cached;
    }

    final AssetBundle b = bundle ?? rootBundle;
    final String assetDir = ModelPath.dirName(assetPath);
    final String entryName = ModelPath.fileName(assetPath);

    String source;
    try {
      source = await b.loadString(assetPath);
    } catch (_) {
      return _fail(
        '内置模型入口不存在：$assetPath · '
        '请把 xxx.model3.json（或 .model.json / .moc3）与 .moc3、纹理放进 '
        '$assetDir/，或在「设定 → 模型」选择本机目录',
      );
    }
    if (source.trim().isEmpty || !source.trim().startsWith('{')) {
      return _fail('内置模型入口不是有效 JSON：$assetPath');
    }

    final List<String> refs = referencesFrom(source);
    if (refs.isEmpty) {
      return _fail(
        '内置模型入口缺少 FileReferences 资源清单：$assetPath · '
        '请确认放的是 Cubism 3 的 .model3.json',
      );
    }
    if (refs.length > _maxRefs) {
      return _fail('内置模型引用文件过多（${refs.length}），已跳过以免占满内存');
    }

    final Directory base = await getApplicationDocumentsDirectory();
    final String targetDir = '${base.path}/live2d/${cfg.id}';
    final String entryTarget = '$targetDir/$entryName';

    // 进程重启后内存缓存为空：靠磁盘标记做「存在性检查」直接复用，
    // 不再把整包 .moc3 / 纹理从 asset 解码、再写一遍（IO 与内存都省掉）。
    // 标记失效（版本变化 / 入口改名 / 任一文件被删）才走下面的完整自检+复制。
    if (await _alreadyInstalled(targetDir, assetPath, entryName, refs)) {
      final ModelInstallResult result = ModelInstallResult(entryTarget);
      _cache[assetPath] = result;
      lastResult = result;
      return result;
    }

    // 先把所有引用都验证一遍，缺任何一个都不写盘、不谎报就绪。
    final List<String> missing = <String>[];
    final Map<String, String> toCopy = <String, String>{};
    for (final String ref in refs) {
      if (_escapes(ref)) {
        missing.add('$ref（引用越界）');
        continue;
      }
      final String key = assetKey(assetDir, ref);
      try {
        final ByteData data = await b.load(key);
        if (data.lengthInBytes == 0) {
          missing.add(ref);
        } else {
          toCopy[key] = ref;
        }
      } catch (_) {
        missing.add(ref);
      }
    }
    if (missing.isNotEmpty) {
      final String sample = missing.take(4).join('、');
      return _fail(
        '内置模型缺少 ${missing.length} 个资源文件（$sample'
        '${missing.length > 4 ? '…' : ''}）· '
        '请补齐 .moc3 / 纹理 / Animation / Exp3 后点「重新自检资源」',
        missing,
      );
    }

    await Directory(targetDir).create(recursive: true);
    await _writeAsset(b, assetPath, entryTarget);
    for (final MapEntry<String, String> e in toCopy.entries) {
      final String rel = ModelPath.normalize(e.value)
          .replaceFirst(RegExp(r'^\./'), '');
      await _writeAsset(b, e.key, '$targetDir/$rel');
    }
    await File('$targetDir/$_markerName').writeAsString(
      json.encode(<String, dynamic>{
        'version': _installVersion,
        'source': assetPath,
        'entry': entryName,
        'files': toCopy.length + 1,
      }),
    );

    final ModelInstallResult result = ModelInstallResult(entryTarget);
    _cache[assetPath] = result;
    lastResult = result;
    return result;
  }

  /// 磁盘标记 + 入口 + 每个引用文件的存在性检查（纯 stat，不读大文件）。
  static Future<bool> _alreadyInstalled(
    String targetDir,
    String assetPath,
    String entryName,
    List<String> refs,
  ) async {
    try {
      final File marker = File('$targetDir/$_markerName');
      if (!await marker.exists()) return false;
      final dynamic decoded = json.decode(await marker.readAsString());
      if (decoded is! Map ||
          decoded['version'] != _installVersion ||
          decoded['source'] != assetPath ||
          decoded['entry'] != entryName) {
        return false;
      }
      if (!await File('$targetDir/$entryName').exists()) return false;
      for (final String ref in refs) {
        // 越界 / 绝对 / URI 引用不参与 stat，避免拼出安装目录之外的路径；
        // 这类引用会在下面的完整自检里被判为缺失。
        if (_escapes(ref) ||
            ref.startsWith('/') ||
            ref.contains('://')) {
          return false;
        }
        final String rel = ModelPath.normalize(ref)
            .replaceFirst(RegExp(r'^\./'), '');
        if (!await File('$targetDir/$rel').exists()) return false;
      }
      return true;
    } catch (_) {
      return false;
    }
  }

  static Future<void> _writeAsset(
    AssetBundle bundle,
    String key,
    String target,
  ) async {
    final ByteData data = await bundle.load(key);
    final File file = File(target);
    await file.create(recursive: true);
    await file.writeAsBytes(
      data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes),
      flush: false,
    );
  }
}
