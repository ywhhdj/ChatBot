import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';

import '../../core/config/model_config.dart';
import '../../core/config/model_path.dart';

/// 适配结果：可直接交给 `Live2DViewController.loadModel` 的两个参数。
class AdaptedEntry {
  const AdaptedEntry({
    required this.dir,
    required this.fileName,
    this.generatedPath = '',
    this.source = '',
    this.warnings = const <String>[],
    this.error = '',
  });

  /// 插件的 modelDir。
  final String dir;
  /// 插件的 modelFileName。
  final String fileName;
  /// 生成的兼容入口绝对路径（空串 = 用原入口）。
  final String generatedPath;
  /// 规范化后的入口 JSON（assets 只读场景交给物化回退写入磁盘）。
  final String source;
  final List<String> warnings;
  final String error;

  bool get ok => error.isEmpty && dir.isNotEmpty && fileName.isNotEmpty;
  bool get generated => generatedPath.isNotEmpty;
}

/// 「拓宽插件解析」适配层（不改依赖、不动 flutter_live2d 二进制）。
///
/// 第三方插件的原生 Core 只认标准 Cubism 3/4/5 `.model3.json`。本层在调用
/// 插件之前，把下列常见但插件不认的包统一转成标准入口：
/// * 只有 `.moc3` + 纹理 / 动作 / 表情、没有入口 JSON（VTS 导出包常见）；
/// * `.model.json` 根层字段、大小写不同的键、Motions/Expressions 是 Map/List；
/// * 带 BOM、`//` / `/* */` 注释、尾逗号的 JSON；
/// * percent-encoded 的中文路径、`./` 前缀、`file://` 引用；
/// * 入口声明缺 Moc / 缺纹理，但同目录里其实有这些文件。
///
/// 做法：容错解析 → 目录补扫 → 生成一份 `__gal_compat_*.model3.json`
/// （与原资源同目录，引用保持相对路径，插件能直接找到），幂等、有上限、
/// 可被扫描器识别并排除，也能在「存储与维护」里一键清理。
/// Cubism 2 的 `.moc` 明确拒绝：它不是 `.moc3`，写多少个 JSON 都救不了。
class ModelEntryAdapter {
  ModelEntryAdapter._();

  static const int maxTextures = 24;
  static const int maxMotions = 64;
  static const int maxExpressions = 64;
  static const int maxFilesVisited = 2000;
  static const String _manifestName = 'resources.json';

  static const Set<String> _textureExts = <String>{
    '.png',
    '.jpg',
    '.jpeg',
    '.webp',
  };
  static const Set<String> _avatarMarkers = <String>{
    'avatar',
    'preview',
    'thumbnail',
    'thumb',
    'icon',
    '头像',
    '封面',
    '预览',
    '缩略图',
  };

  static final Map<String, AdaptedEntry> _cache = <String, AdaptedEntry>{};
  static final Map<String, ModelEntryDoc> _docCache =
      <String, ModelEntryDoc>{};
  static final Set<String> _generated = <String>{};

  static void invalidate([String? path]) {
    if (path == null) {
      _cache.clear();
      _docCache.clear();
    } else {
      _cache.remove(path);
      _docCache.remove(path);
    }
  }

  /// 清理本进程生成过的兼容入口（不碰用户任何原始模型文件）。
  static Future<int> disposeGenerated() async {
    int removed = 0;
    for (final String p in _generated.toList(growable: false)) {
      try {
        final File f = File(p);
        if (await f.exists()) {
          await f.delete();
          removed++;
        }
      } catch (_) {}
    }
    _generated.clear();
    _cache.clear();
    _docCache.clear();
    return removed;
  }

  /// 生成入口的稳定名字：路径 base64Url 前 16 位，跨重启一致、可幂等复用。
  static String _hash(String path) {
    final String raw = base64Url
        .encode(utf8.encode(ModelPath.canonicalPath(path)))
        .replaceAll('=', '');
    return raw.length > 16 ? raw.substring(0, 16) : raw;
  }

  static String _generatedName(String sourcePath) =>
      '${ModelPath.generatedEntryPrefix}${_hash(sourcePath)}.model3.json';

  /// 主入口：把任意候选模型配置适配成插件能吃的一对参数。
  static Future<AdaptedEntry> resolve(
    ModelConfig cfg, {
    AssetBundle? bundle,
  }) async {
    if (cfg.path.isEmpty) {
      return const AdaptedEntry(
        dir: '',
        fileName: '',
        error: '未选择模型 · 请到「设定 → 模型」选模型或选择目录',
      );
    }
    final AdaptedEntry? cached = _cache[cfg.path];
    if (cached != null &&
        (cached.generatedPath.isEmpty ||
            File(cached.generatedPath).existsSync())) {
      return cached;
    }
    return cfg.isAsset
        ? _resolveAsset(cfg, bundle)
        : _resolveLocal(cfg);
  }

  /// 只做解析 / 补扫，返回规范化文档（演出资源页、assets 自检共用）。
  static Future<ModelEntryDoc> documentFor(
    ModelConfig cfg, {
    AssetBundle? bundle,
  }) async {
    final ModelEntryDoc? cached = _docCache[cfg.path];
    if (cached != null) return cached;
    final ModelEntryDoc doc = cfg.isAsset
        ? await _assetDoc(cfg, bundle)
        : _localDoc(cfg.path);
    _docCache[cfg.path] = doc;
    return doc;
  }

  // ---------------------------------------------------------------------------
  // 本机目录
  // ---------------------------------------------------------------------------

  static Future<AdaptedEntry> _resolveLocal(ModelConfig cfg) async {
    final String path = ModelPath.normalize(cfg.path);
    final String dir = ModelPath.dirName(path);
    final String entryName = ModelPath.fileName(path);
    if (dir.isEmpty) {
      return const AdaptedEntry(
        dir: '',
        fileName: '',
        error: '模型路径没有目录，无法定位资源 · 请重新选择目录',
      );
    }

    final ModelEntryDoc doc = _localDoc(path);
    if (doc.unsupported.isNotEmpty) {
      return AdaptedEntry(dir: '', fileName: '', error: doc.unsupported);
    }
    if (doc.moc.isEmpty) {
      return AdaptedEntry(
        dir: '',
        fileName: '',
        error: '目录里没有找到 .moc3（模型本体）：$dir · '
            '插件只能解析 Cubism 3+ 的 .moc3，请把完整模型放进来',
      );
    }

    // 已经是干净的标准入口，且引用的资源都在：不写任何文件，直接用。
    final bool standardName = entryName.toLowerCase().endsWith('.model3.json');
    final bool needsRewrite = doc.needsRewrite || !standardName;
    if (!needsRewrite) {
      final String? check = await ModelPath.checkLocalAsync(path);
      if (check == null) {
        final AdaptedEntry result = AdaptedEntry(
          dir: dir,
          fileName: entryName,
          warnings: doc.warnings,
        );
        _cache[cfg.path] = result;
        return result;
      }
      // 引用缺失也生成一份补齐后的入口，让 checkLocal 能明确列出缺什么。
    }

    final ModelEntryDoc finalDoc = _pruneDoc(doc, dir);
    if (finalDoc.moc.isEmpty) {
      return AdaptedEntry(
        dir: '',
        fileName: '',
        error: '目录里没有可用的 .moc3（模型本体）：$dir · '
            '入口声明的 Moc 文件不存在，请把完整模型放进来',
      );
    }
    final String outName = _generatedName(path);
    final String target = ModelPath.join(dir, outName);
    final String source = finalDoc.toSource();
    try {
      final File f = File(target);
      final bool same =
          await f.exists() && await f.readAsString() == source;
      if (!same) {
        await f.writeAsString(source, flush: false);
      }
    } catch (e) {
      return AdaptedEntry(
        dir: '',
        fileName: '',
        error: '模型目录只读，无法生成兼容入口：$dir · '
            '请把模型放到内部存储目录（不是 SAF / 外置卡 URI）后重试 · $e',
      );
    }
    _generated.add(target);
    final List<String> warnings = <String>[
      ...finalDoc.warnings,
      '已生成兼容入口 $outName（${_reason(finalDoc, standardName, path)}）· '
          '原模型文件未改动，可在「存储」页一键清理',
    ];
    final AdaptedEntry result = AdaptedEntry(
      dir: dir,
      fileName: outName,
      generatedPath: target,
      source: source,
      warnings: warnings,
    );
    _cache[cfg.path] = result;
    return result;
  }

  static String _reason(ModelEntryDoc doc, bool standardName, String path) {
    if (path.toLowerCase().endsWith('.moc3')) return '原入口是纯 .moc3';
    if (!standardName) return '原入口不是 .model3.json';
    if (doc.moc.isEmpty) return '自动补了 .moc3';
    if (doc.warnings.isNotEmpty) return doc.warnings.first;
    return '入口引用有缺失';
  }

  /// 生成兼容入口前做一次「引用剪枝」：入口里写了但目录里没有的纹理 /
  /// 动作 / 表情全部丢掉，只保留真实存在的文件。
  /// 这是「文件齐全但入口声明过期」这类包能加载的关键。
  static ModelEntryDoc _pruneDoc(ModelEntryDoc doc, String dir) {
    bool exists(String r) =>
        r.isNotEmpty && File(ModelPath.join(dir, r)).existsSync();
    String keep(String r) => exists(r) ? r : '';

    final List<String> textures =
        doc.textures.where(exists).take(maxTextures).toList();
    final Map<String, List<Map<String, dynamic>>> motions =
        <String, List<Map<String, dynamic>>>{};
    for (final MapEntry<String, List<Map<String, dynamic>>> e
        in doc.motions.entries) {
      final List<Map<String, dynamic>> kept = e.value
          .where((Map<String, dynamic> m) =>
              exists((m['File'] ?? '').toString()))
          .take(maxMotions)
          .toList();
      if (kept.isNotEmpty) motions[e.key] = kept;
    }
    final List<Map<String, dynamic>> expressions = doc.expressions
        .where((Map<String, dynamic> m) =>
            exists((m['File'] ?? '').toString()))
        .take(maxExpressions)
        .toList();

    final bool pruned = textures.length != doc.textures.length ||
        expressions.length != doc.expressions.length ||
        motions.values.fold<int>(0, (int n, List<Map<String, dynamic>> l) =>
            n + l.length) !=
            doc.motions.values.fold<int>(0,
                (int n, List<Map<String, dynamic>> l) => n + l.length);
    return ModelEntryDoc(
      version: 3,
      moc: keep(doc.moc),
      textures: textures,
      physics: keep(doc.physics),
      pose: keep(doc.pose),
      displayInfo: keep(doc.displayInfo),
      userData: keep(doc.userData),
      motions: motions,
      expressions: expressions,
      warnings: <String>[
        ...doc.warnings,
        if (pruned) '入口声明的部分资源不存在，兼容入口只保留实际存在的文件',
      ],
      needsRewrite: true,
      unsupported: doc.unsupported,
    );
  }

  static ModelEntryDoc _localDoc(String path) {
    final String dir = ModelPath.dirName(ModelPath.normalize(path));
    final String entryName = ModelPath.fileName(path);
    ModelEntryDoc base = const ModelEntryDoc(needsRewrite: true);
    String source = '';
    if (!path.toLowerCase().endsWith('.moc3')) {
      try {
        final File f = File(path);
        if (f.existsSync() && f.lengthSync() <= 2 * 1024 * 1024) {
          source = f.readAsStringSync();
          base = ModelPath.parseEntry(source);
        }
      } catch (_) {}
    }
    if (source.trim().isEmpty || !source.trim().startsWith('{')) {
      base = const ModelEntryDoc(
        needsRewrite: true,
        warnings: <String>['没有可读的入口 JSON，按目录资源生成兼容入口'],
      );
    }
    if (base.unsupported.isNotEmpty) return base;

    // 纯 .moc3 入口时，它本身就是模型本体：不能把自己排除掉。
    // 只有入口是 JSON 才需要把它从「动作 / 纹理补扫」里排除。
    final String excludeEntry =
        path.toLowerCase().endsWith('.moc3') ? '' : entryName;
    final _DirScan scan = _scanDir(dir, exclude: excludeEntry);
    // 入口可能声明了一个并不存在的 .moc3（导出时改名 / 只拷了一半）。
    // 优先用真实存在的声明，否则退回目录里扫到的 .moc3，避免生成空壳入口。
    final bool declaredMocExists = base.moc.isNotEmpty &&
        File(ModelPath.join(dir, base.moc)).existsSync();
    final String moc = declaredMocExists ? base.moc : scan.moc;
    final List<String> textures = <String>[
      ...base.textures,
      for (final String t in scan.textures)
        if (!base.textures.contains(t)) t,
    ].take(maxTextures).toList();
    final Map<String, List<Map<String, dynamic>>> motions =
        base.motions.isNotEmpty
            ? base.motions
            : <String, List<Map<String, dynamic>>>{'Idle': scan.motions};
    final List<Map<String, dynamic>> expressions =
        base.expressions.isNotEmpty ? base.expressions : scan.expressions;
    final bool inferred = (!declaredMocExists && scan.moc.isNotEmpty) ||
        (base.textures.isEmpty && scan.textures.isNotEmpty) ||
        (base.motions.isEmpty && scan.motions.isNotEmpty) ||
        (base.expressions.isEmpty && scan.expressions.isNotEmpty);
    final bool standardName = ModelPath.fileName(path)
        .toLowerCase()
        .endsWith('.model3.json');

    return ModelEntryDoc(
      version: 3,
      moc: moc,
      textures: textures,
      physics: base.physics.isNotEmpty ? base.physics : scan.physics,
      pose: base.pose.isNotEmpty ? base.pose : scan.pose,
      displayInfo: base.displayInfo.isNotEmpty
          ? base.displayInfo
          : scan.displayInfo,
      userData: base.userData.isNotEmpty ? base.userData : scan.userData,
      motions: motions,
      expressions: expressions,
      warnings: <String>[
        ...base.warnings,
        if (!declaredMocExists && scan.moc.isNotEmpty)
          '入口未声明或声明的 Moc 不存在，已从目录补上 ${scan.moc}',
        if (base.textures.isEmpty && scan.textures.isNotEmpty)
          '已从目录补上 ${scan.textures.length} 张纹理',
        if (base.motions.isEmpty && scan.motions.isNotEmpty)
          '已从目录补上 ${scan.motions.length} 个动作（归入 Idle 组）',
      ],
      needsRewrite: base.needsRewrite ||
          inferred ||
          !standardName ||
          path.toLowerCase().endsWith('.moc3'),
      unsupported: base.unsupported,
    );
  }

  static _DirScan _scanDir(String dir, {String exclude = ''}) {
    String moc = '';
    final List<String> textures = <String>[];
    final List<Map<String, dynamic>> motions = <Map<String, dynamic>>[];
    final List<Map<String, dynamic>> expressions = <Map<String, dynamic>>[];
    String physics = '';
    String pose = '';
    String displayInfo = '';
    String userData = '';
    final Directory d = Directory(dir);
    if (!d.existsSync()) {
      return _DirScan(
        moc: moc,
        textures: textures,
        motions: motions,
        expressions: expressions,
        physics: physics,
        pose: pose,
        displayInfo: displayInfo,
        userData: userData,
      );
    }
    int visited = 0;
    try {
      for (final FileSystemEntity e
          in d.listSync(recursive: true, followLinks: false)) {
        if (visited++ >= maxFilesVisited) break;
        if (e is! File) continue;
        final String name = ModelPath.fileName(e.path);
        final String lower = name.toLowerCase();
        if (lower.startsWith('.') ||
            ModelPath.isGeneratedEntry(name) ||
            lower == _manifestName ||
            lower == exclude.toLowerCase()) {
          continue;
        }
        final String rel = _relative(dir, e.path);
        if (rel.isEmpty || rel.startsWith('../')) continue;
        if (lower.endsWith('.moc3')) {
          if (moc.isEmpty) moc = rel;
        } else if (_textureExts.any((String x) => lower.endsWith(x))) {
          if (textures.length < maxTextures &&
              !_avatarMarkers.any((String m) => lower.contains(m))) {
            textures.add(rel);
          }
        } else if (lower.endsWith('.motion3.json')) {
          if (motions.length < maxMotions) {
            motions.add(<String, dynamic>{
              'File': rel,
              'Name': ModelPath.modelTitle(rel),
            });
          }
        } else if (lower.endsWith('.exp3.json')) {
          if (expressions.length < maxExpressions) {
            expressions.add(<String, dynamic>{
              'File': rel,
              'Name': ModelPath.modelTitle(rel),
            });
          }
        } else if (lower.endsWith('.physics3.json') && physics.isEmpty) {
          physics = rel;
        } else if (lower.endsWith('.pose3.json') && pose.isEmpty) {
          pose = rel;
        } else if (lower.endsWith('.displayinfo3.json') &&
            displayInfo.isEmpty) {
          displayInfo = rel;
        } else if (lower.endsWith('.userdata3.json') && userData.isEmpty) {
          userData = rel;
        }
      }
    } catch (_) {
      // 某个子目录无权限：保留已扫到的部分。
    }
    return _DirScan(
      moc: moc,
      textures: textures,
      motions: motions,
      expressions: expressions,
      physics: physics,
      pose: pose,
      displayInfo: displayInfo,
      userData: userData,
    );
  }

  static String _relative(String dir, String full) {
    final String d = ModelPath.canonicalPath(dir);
    final String f = ModelPath.canonicalPath(full);
    if (!f.toLowerCase().startsWith('${d.toLowerCase()}/') ||
        f.length <= d.length + 1) {
      return '';
    }
    return f.substring(d.length + 1);
  }

  // ---------------------------------------------------------------------------
  // assets 内置（bundle 只读：只产出规范化文本，由物化回退写盘）
  // ---------------------------------------------------------------------------

  static Future<AdaptedEntry> _resolveAsset(
    ModelConfig cfg,
    AssetBundle? bundle,
  ) async {
    final AssetBundle b = bundle ?? rootBundle;
    final String cfgPath = ModelPath.normalize(cfg.path);
    final String assetDir = ModelPath.dirName(cfgPath);
    final (String entryPath, String entryName) =
        await _findAssetEntry(b, cfgPath, assetDir);
    if (entryPath.isEmpty) {
      return AdaptedEntry(
        dir: '',
        fileName: '',
        error: '内置模型缺少入口 .model3.json，且 resources.json 里没有 '
            '"entry" / .model3.json 清单：$assetDir · '
            '请把 Cubism 导出包的 .model3.json / .moc3 / 纹理一起放进 assets',
      );
    }
    final ModelEntryDoc doc = await _assetDoc(cfg, bundle);
    if (doc.unsupported.isNotEmpty) {
      return AdaptedEntry(dir: '', fileName: '', error: doc.unsupported);
    }
    final AdaptedEntry result = AdaptedEntry(
      dir: assetDir,
      fileName: entryName,
      source: doc.toSource(),
      warnings: <String>[
        ...doc.warnings,
        if (doc.needsRewrite)
          '内置入口不是标准结构，物化回退时会写入规范化副本',
      ],
    );
    _cache[cfg.path] = result;
    return result;
  }

  static Future<ModelEntryDoc> _assetDoc(
    ModelConfig cfg,
    AssetBundle? bundle,
  ) async {
    final AssetBundle b = bundle ?? rootBundle;
    final String cfgPath = ModelPath.normalize(cfg.path);
    final String assetDir = ModelPath.dirName(cfgPath);
    final (String entryPath, _) =
        await _findAssetEntry(b, cfgPath, assetDir);
    String source = '';
    if (entryPath.isNotEmpty) {
      try {
        source = await b.loadString(entryPath);
      } catch (_) {}
    }
    ModelEntryDoc base = source.trim().startsWith('{')
        ? ModelPath.parseEntry(source)
        : const ModelEntryDoc(
            needsRewrite: true,
            warnings: <String>['内置入口不可读'],
          );
    if (base.unsupported.isNotEmpty) return base;

    // assets 不是文件系统：从 resources.json 清单补 Moc / 纹理 / 演出资源。
    final List<String> manifest = await _manifestFiles(b, assetDir);
    String moc = base.moc;
    if (moc.isEmpty) {
      for (final String f in manifest) {
        if (f.toLowerCase().endsWith('.moc3')) {
          moc = f;
          break;
        }
      }
    }
    final List<String> textures = <String>[
      ...base.textures,
      for (final String f in manifest)
        if (_textureExts.any((String x) => f.toLowerCase().endsWith(x)) &&
            !base.textures.contains(f))
          f,
    ].take(maxTextures).toList();
    final List<Map<String, dynamic>> motions =
        <Map<String, dynamic>>[];
    final List<Map<String, dynamic>> expressions =
        <Map<String, dynamic>>[];
    if (base.motions.isEmpty) {
      for (final String f in manifest) {
        if (motions.length >= maxMotions) break;
        if (f.toLowerCase().endsWith('.motion3.json')) {
          motions.add(<String, dynamic>{
            'File': f,
            'Name': ModelPath.modelTitle(f),
          });
        }
      }
    }
    if (base.expressions.isEmpty) {
      for (final String f in manifest) {
        if (expressions.length >= maxExpressions) break;
        if (f.toLowerCase().endsWith('.exp3.json')) {
          expressions.add(<String, dynamic>{
            'File': f,
            'Name': ModelPath.modelTitle(f),
          });
        }
      }
    }
    base = ModelEntryDoc(
      version: 3,
      moc: moc,
      textures: textures,
      physics: base.physics,
      pose: base.pose,
      displayInfo: base.displayInfo,
      userData: base.userData,
      motions: base.motions.isNotEmpty
          ? base.motions
          : (motions.isEmpty
              ? const <String, List<Map<String, dynamic>>>{}
              : <String, List<Map<String, dynamic>>>{'Idle': motions}),
      expressions: base.expressions.isNotEmpty
          ? base.expressions
          : expressions,
      warnings: <String>[
        ...base.warnings,
        if (base.moc.isEmpty && moc.isNotEmpty) '已从清单补上 Moc：$moc',
      ],
      needsRewrite: base.needsRewrite || base.moc.isEmpty,
      unsupported: base.unsupported,
    );
    return base;
  }

  static Future<(String, String)> _findAssetEntry(
    AssetBundle b,
    String cfgPath,
    String assetDir,
  ) async {
    try {
      await b.loadString(cfgPath);
      return (cfgPath, ModelPath.fileName(cfgPath));
    } catch (_) {}
    final List<String> manifest = await _manifestFiles(b, assetDir);
    String virtual = '';
    for (final String f in manifest) {
      final String lower = f.toLowerCase();
      if (!lower.endsWith('.model3.json') && !lower.endsWith('.model.json')) {
        continue;
      }
      final String candidate =
          assetDir.isEmpty ? f : '$assetDir/${_stripDot(f)}';
      if (virtual.isEmpty) virtual = candidate;
      try {
        final String source = await b.loadString(candidate);
        if (source.contains('FileReferences') ||
            source.contains('"Moc"') ||
            source.contains('"Textures"')) {
          return (candidate, ModelPath.fileName(candidate));
        }
      } catch (_) {}
    }
    // VTS 导出包常见：清单写了入口名，但包里没有 .model3.json。
    // 返回一个「虚拟入口」：文本由适配层从清单生成，物化回退时写盘。
    if (virtual.isNotEmpty) {
      return (virtual, ModelPath.fileName(virtual));
    }
    return ('', '');
  }

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
      for (final String key in <String>[
        'entry',
        'entries',
        'files',
        'textures',
        'motions',
        'expressions',
      ]) {
        _collectManifest(decoded[key], out);
      }
      return out.take(maxFilesVisited).toList();
    } catch (_) {
      return const <String>[];
    }
  }

  static void _collectManifest(dynamic v, List<String> out) {
    if (v is String) {
      final String s = _stripDot(v);
      if (s.isNotEmpty) out.add(s);
    } else if (v is List) {
      for (final dynamic e in v) {
        _collectManifest(e, out);
      }
    } else if (v is Map) {
      for (final dynamic e in v.values) {
        _collectManifest(e, out);
      }
    }
  }

  static String _stripDot(String s) => ModelPath.normalize(s)
      .replaceFirst(RegExp(r'^\./'), '');
}

class _DirScan {
  const _DirScan({
    required this.moc,
    required this.textures,
    required this.motions,
    required this.expressions,
    required this.physics,
    required this.pose,
    required this.displayInfo,
    required this.userData,
  });

  final String moc;
  final List<String> textures;
  final List<Map<String, dynamic>> motions;
  final List<Map<String, dynamic>> expressions;
  final String physics;
  final String pose;
  final String displayInfo;
  final String userData;
}
