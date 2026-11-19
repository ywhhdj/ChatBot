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
    this.entryName = '',
    this.assetDir = '',
    this.warnings = const <String>[],
    this.verifiedOnly = false,
  });

  /// 可直接交给 Live2D 插件的入口路径；失败时为空串。
  /// `verifiedOnly=true` 时是原始 assets 路径（插件会自己解压 assets 目录），
  /// 否则是物化到应用文档目录的绝对路径。
  final String path;
  final String error;
  final List<String> missing;

  /// 真实入口文件名（可能是中文，不能再用配置里写死的那个名字）。
  final String entryName;

  /// 入口所在的 assets 目录，插件原生通道用 `modelDir` 传它。
  final String assetDir;

  /// 非致命但值得显示的提醒：自动发现入口、纹理过大、子目录可能未声明等。
  final List<String> warnings;

  /// true = 只做了存在性预检、没有把文件复制到磁盘。
  final bool verifiedOnly;

  bool get ok => error.isEmpty && path.isNotEmpty;
  bool get hasWarnings => warnings.isNotEmpty;
}

/// 内置 assets 模型的资源预检 / 物化。
///
/// 接入 VTube Studio 导出包后重新梳理了策略：
/// * **主通道是插件原生的 assets 支持**：`flutter_live2d` 的文档明确写了
///   「Asset directories are copied to the app's temp folder on first load」，
///   所以只要 pubspec 把**每个子目录**都声明了，直接传
///   `modelDir: 'assets/live2d/deepseek/'` + 真实入口名就行。
///   原来的「把整个模型复制到应用文档目录」是多余的：4096 纹理有 5 张，
///   复制一次就多占 300MB+ 磁盘，还可能在原生侧踩中文路径。
/// * `verify()` 只预检不复制：逐个 `rootBundle.load` 确认 FileReferences
///   里的文件真的在包里。**这一步能直接抓到「纹理子目录没在 pubspec 声明」**，
///   因为没声明的文件根本不在 asset bundle 里。
/// * 入口名不再写死：配置的 path 读不到时，会读同目录 `resources.json` 的
///   `"entry"` 字段自动发现（VTube Studio 导出的名字往往不是我们预设的）。
/// * 顺带读 PNG 文件头拿纹理尺寸，4096 大纹理在移动端容易 OOM 或超出
///   `GL_MAX_TEXTURE_SIZE`，给出预警而不是让用户对着透明画面猜。
/// * `materialize()` 保留为**回退**：万一插件的原生 assets 通道加载失败，
///   再复制成绝对路径试一次。
class ModelAssetInstaller {
  ModelAssetInstaller._();

  static const String _markerName = '.installed.json';
  static const String _manifestName = 'resources.json';
  static const int _installVersion = 2;
  static const int _maxRefs = 512;

  /// 移动端常见的纹理上限：超过它要提醒用户（不是硬失败）。
  static const int _warnTextureEdge = 2048;
  static const int _hardTextureEdge = 4096;

  static final Map<String, ModelInstallResult> _cache =
      <String, ModelInstallResult>{};

  /// 最近一次自检结果：设置页「存储与维护」用它展示缺失清单与提醒。
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
  /// percent-encode（例如 `大肥鱼.4096/texture_00.png` → `%E5%A4%A7...`），
  /// 而 rootBundle.load 要的是原始 asset key。这里做纯字符串规范化。
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

  /// 纯函数：只读 PNG 头 24 字节就能拿到宽高，不解码整张图。
  /// 返回 null 表示不是 PNG / 数据太短。
  static (int, int)? pngSize(Uint8List bytes) {
    if (bytes.length < 24) return null;
    const List<int> signature = <int>[
      0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
    ];
    for (int i = 0; i < 8; i++) {
      if (bytes[i] != signature[i]) return null;
    }
    final int w = (bytes[16] << 24) |
        (bytes[17] << 16) |
        (bytes[18] << 8) |
        bytes[19];
    final int h = (bytes[20] << 24) |
        (bytes[21] << 16) |
        (bytes[22] << 8) |
        bytes[23];
    if (w <= 0 || h <= 0) return null;
    return (w, h);
  }

  /// 把纹理尺寸整理成给用户看的风险提示。
  static List<String> textureWarnings(List<(int, int)> sizes) {
    if (sizes.isEmpty) return const <String>[];
    int maxEdge = 0;
    double totalMb = 0;
    for (final (int, int) s in sizes) {
      final int edge = s.$1 > s.$2 ? s.$1 : s.$2;
      if (edge > maxEdge) maxEdge = edge;
      totalMb += s.$1 * s.$2 * 4 / (1024 * 1024);
    }
    final List<String> out = <String>[];
    out.add('检测到 ${sizes.length} 张纹理，最大边 ${maxEdge}px，'
        '按 RGBA 估算约 ${totalMb.toStringAsFixed(0)}MB 显存/内存');
    if (maxEdge > _hardTextureEdge) {
      out.add('纹理边长超过 ${_hardTextureEdge}px：多数移动 GPU 的 '
          'GL_MAX_TEXTURE_SIZE 只有 4096，可能直接上传失败或黑屏');
    } else if (maxEdge > _warnTextureEdge) {
      out.add('大纹理在部分中低端机上可能超出 GL_MAX_TEXTURE_SIZE(2048/4096) '
          '或触发 GL_OUT_OF_MEMORY；建议用 Cubism Editor 重新导出 2048 版本');
    }
    if (totalMb > 256) {
      out.add('纹理总量偏大，建议改用 2048 目录或压缩纹理，避免启动即 OOM');
    }
    return out;
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

  /// 找到真正存在的入口路径：优先用配置里登记的，读不到就查 resources.json
  /// 的 `"entry"` 字段自动发现。返回 (真实 assetPath, 入口文件名, 是否自动发现)。
  static Future<(String, String, bool)> _resolveEntry(
    AssetBundle b,
    String cfgPath,
  ) async {
    final String normalized = ModelPath.normalize(cfgPath);
    final String dir = ModelPath.dirName(normalized);
    try {
      await b.loadString(normalized);
      return (normalized, ModelPath.fileName(normalized), false);
    } catch (_) {
      // 登记的名字不对（例如写死 deepseek.model3.json 而实际是 大肥鱼.model3.json）。
    }
    try {
      final String raw = await b.loadString(
        dir.isEmpty ? _manifestName : '$dir/$_manifestName',
      );
      final dynamic decoded = json.decode(raw);
      if (decoded is Map) {
        final String entry =
            ModelPath.normalize((decoded['entry'] ?? '').toString())
                .replaceFirst(RegExp(r'^\./'), '');
        if (entry.isNotEmpty && entry.toLowerCase().endsWith('.json')) {
          final String candidate = dir.isEmpty ? entry : '$dir/$entry';
          await b.loadString(candidate);
          return (candidate, ModelPath.fileName(candidate), true);
        }
      }
    } catch (_) {
      // 清单不存在或字段缺失：交给下面的错误信息说明。
    }
    return ('', '', false);
  }

  /// 读取同目录清单里的 `textures` / `files`，用于补充校验与显眼提示。
  static Future<List<String>> _manifestFiles(
    AssetBundle b,
    String assetDir,
  ) async {
    if (assetDir.isEmpty) return const <String>[];
    try {
      final String raw = await b.loadString('$assetDir/$_manifestName');
      final dynamic decoded = json.decode(raw);
      if (decoded is! Map) return const <String>[];
      final List<String> out = <String>[];
      for (final String key in <String>['textures', 'files']) {
        final dynamic list = decoded[key];
        if (list is List) {
          for (final dynamic e in list) {
            if (e is String) {
              out.add(ModelPath.normalize(e)
                  .replaceFirst(RegExp(r'^\./'), ''));
            }
          }
        }
      }
      return out.take(_maxRefs).toList();
    } catch (_) {
      return const <String>[];
    }
  }

  /// **主通道**：只预检不复制，验证所有引用文件确实被 pubspec 打进了包。
  /// 成功时 `path` 是原始 assets 路径，`assetDir` 可直接作为插件的 modelDir。
  static Future<ModelInstallResult> verify(
    ModelConfig cfg, {
    AssetBundle? bundle,
  }) async {
    final String cfgPath = ModelPath.normalize(cfg.path);
    if (!cfgPath.startsWith('assets/')) {
      // 本机目录不需要 asset 预检，交给 ModelPath.checkLocal。
      return ModelInstallResult(cfgPath,
          entryName: ModelPath.fileName(cfgPath));
    }

    final ModelInstallResult? cached = _cache[cfgPath];
    if (cached != null && cached.ok && cached.verifiedOnly) {
      lastResult = cached;
      return cached;
    }

    final AssetBundle b = bundle ?? rootBundle;
    final String assetDir = ModelPath.dirName(cfgPath);
    final (String entryPath, String entryName, bool discovered) =
        await _resolveEntry(b, cfgPath);
    if (entryPath.isEmpty) {
      final String manifest =
          assetDir.isEmpty ? _manifestName : '$assetDir/$_manifestName';
      return _fail(
        '内置模型入口不存在：$cfgPath · 也没能从 $manifest 的 "entry" 字段'
        '自动发现入口。请确认 .model3.json 真的在 '
        '${assetDir.isEmpty ? '.' : assetDir}/ 下，且 pubspec 声明了该目录',
      );
    }

    String source;
    try {
      source = await b.loadString(entryPath);
    } catch (_) {
      return _fail('内置模型入口读不出来：$entryPath');
    }
    if (source.trim().isEmpty || !source.trim().startsWith('{')) {
      return _fail('内置模型入口不是有效 JSON：$entryPath');
    }

    final List<String> refs = referencesFrom(source);
    // 清单里的纹理/文件也纳入校验：它们即使没被 FileReferences 写出，
    // 也能在这里抓到「子目录没声明」的问题。
    final List<String> manifestFiles = await _manifestFiles(b, assetDir);
    final Set<String> allRefs = <String>{...refs, ...manifestFiles};
    if (allRefs.isEmpty) {
      return _fail(
        '内置模型入口缺少 FileReferences 资源清单：$entryPath · '
        '请确认放的是 Cubism 3/4 的 .model3.json',
      );
    }
    if (allRefs.length > _maxRefs) {
      return _fail('内置模型引用文件过多（${allRefs.length}），已跳过以免占满内存');
    }

    final List<String> missing = <String>[];
    final List<(int, int)> sizes = <(int, int)>[];
    for (final String ref in allRefs) {
      if (_escapes(ref)) {
        missing.add('$ref（引用越界）');
        continue;
      }
      final String key = assetKey(assetDir, ref);
      try {
        final ByteData data = await b.load(key);
        if (data.lengthInBytes == 0) {
          missing.add(ref);
          continue;
        }
        // 只读已经在内存里的 ByteData 前 24 字节，不额外解码图片。
        final (int, int)? size = pngSize(
          data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes),
        );
        if (size != null) sizes.add(size);
      } catch (_) {
        missing.add(ref);
      }
    }

    final List<String> warnings = <String>[];
    if (discovered) {
      warnings.add('配置的入口名和实际文件不一致，已自动采用 '
          'resources.json 里的入口：$entryName · 建议同步更新 '
          'ModelConfig.available.path');
    }
    // 缺的引用里只要有子目录文件，就把「pubspec 必须逐条声明」这句话顶到最前。
    final bool missingSubdir = missing.any((String r) => r.contains('/'));
    if (missingSubdir) {
      warnings.add('Flutter 的 assets 声明不递归：纹理 / Animation / Exp3 等'
          '子目录必须在 pubspec.yaml 里各写一行，否则文件不会进包');
    }
    warnings.addAll(textureWarnings(sizes));

    if (missing.isNotEmpty) {
      // 去重 + 把最可能的原因放前面
      final List<String> unique = missing.toSet().toList();
      final String sample = unique.take(5).join('、');
      final String hint = missingSubdir
          ? '· 其中含子目录文件，请检查 pubspec.yaml 是否漏声明了 '
              '「大肥鱼.4096/」这类纹理目录'
          : '· 请补齐 .moc3 / 纹理 / Animation / Exp3 后点「重新自检资源」';
      return _fail(
        '内置模型缺少 ${unique.length} 个资源文件（$sample'
        '${unique.length > 5 ? '…' : ''}） $hint',
        unique,
      );
    }

    final ModelInstallResult result = ModelInstallResult(
      entryPath,
      entryName: entryName,
      assetDir: assetDir,
      warnings: warnings,
      verifiedOnly: true,
    );
    _cache[cfgPath] = result;
    lastResult = result;
    return result;
  }

  /// **回退通道**：把内置模型连同引用资源复制到应用文档目录，返回真实绝对路径。
  /// 只在插件原生 assets 通道明确失败时才调用，避免每次启动多复制几百 MB。
  static Future<ModelInstallResult> materialize(
    ModelConfig cfg, {
    AssetBundle? bundle,
  }) async {
    final String cfgPath = ModelPath.normalize(cfg.path);
    if (!cfgPath.startsWith('assets/')) {
      return ModelInstallResult(cfgPath,
          entryName: ModelPath.fileName(cfgPath));
    }

    final ModelInstallResult? cached = _cache['$cfgPath#materialized'];
    if (cached != null && cached.ok && !cached.verifiedOnly &&
        File(cached.path).existsSync()) {
      lastResult = cached;
      return cached;
    }

    final AssetBundle b = bundle ?? rootBundle;
    final String assetDir = ModelPath.dirName(cfgPath);
    final (String entryPath, String entryName, _) =
        await _resolveEntry(b, cfgPath);
    if (entryPath.isEmpty) {
      return _fail('内置模型入口不存在：$cfgPath（物化回退也无法定位入口）');
    }

    String source;
    try {
      source = await b.loadString(entryPath);
    } catch (_) {
      return _fail('内置模型入口读不出来：$entryPath');
    }
    final List<String> refs = referencesFrom(source);
    final List<String> manifestFiles = await _manifestFiles(b, assetDir);
    final Set<String> allRefs = <String>{...refs, ...manifestFiles};
    if (allRefs.isEmpty) {
      return _fail('内置模型入口缺少 FileReferences 资源清单：$entryPath');
    }

    final Directory base = await getApplicationDocumentsDirectory();
    final String targetDir = '${base.path}/live2d/${cfg.id}';
    final String entryTarget = '$targetDir/$entryName';

    if (await _alreadyInstalled(
      targetDir, entryPath, entryName, allRefs.toList(),
    )) {
      final ModelInstallResult result = ModelInstallResult(
        entryTarget,
        entryName: entryName,
        assetDir: assetDir,
      );
      _cache['$cfgPath#materialized'] = result;
      lastResult = result;
      return result;
    }

    final List<String> missing = <String>[];
    final Map<String, String> toCopy = <String, String>{};
    for (final String ref in allRefs) {
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
          toCopy[key] = ModelPath.normalize(ref)
              .replaceFirst(RegExp(r'^\./'), '');
        }
      } catch (_) {
        missing.add(ref);
      }
    }
    if (missing.isNotEmpty) {
      final String sample = missing.take(4).join('、');
      return _fail(
        '物化回退失败，缺 ${missing.length} 个资源文件（$sample）· '
        '多半是 pubspec 漏声明了纹理子目录',
        missing,
      );
    }

    await Directory(targetDir).create(recursive: true);
    await _writeAsset(b, entryPath, entryTarget);
    for (final MapEntry<String, String> e in toCopy.entries) {
      await _writeAsset(b, e.key, '$targetDir/${e.value}');
    }
    await File('$targetDir/$_markerName').writeAsString(
      json.encode(<String, dynamic>{
        'version': _installVersion,
        'source': entryPath,
        'entry': entryName,
        'files': toCopy.length + 1,
      }),
    );

    final ModelInstallResult result = ModelInstallResult(
      entryTarget,
      entryName: entryName,
      assetDir: assetDir,
    );
    _cache['$cfgPath#materialized'] = result;
    lastResult = result;
    return result;
  }

  /// 磁盘标记 + 入口 + 每个引用文件的存在性检查（纯 stat，不读大文件）。
  static Future<bool> _alreadyInstalled(
    String targetDir,
    String entryPath,
    String entryName,
    List<String> refs,
  ) async {
    try {
      final File marker = File('$targetDir/$_markerName');
      if (!await marker.exists()) return false;
      final dynamic decoded = json.decode(await marker.readAsString());
      if (decoded is! Map ||
          decoded['version'] != _installVersion ||
          decoded['source'] != entryPath ||
          decoded['entry'] != entryName) {
        return false;
      }
      if (!await File('$targetDir/$entryName').exists()) return false;
      for (final String ref in refs) {
        if (_escapes(ref) || ref.startsWith('/') || ref.contains('://')) {
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
