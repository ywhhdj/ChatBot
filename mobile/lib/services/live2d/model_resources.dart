import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';

import '../../core/config/model_config.dart';
import '../../core/config/model_motion.dart';
import '../../core/config/model_path.dart';
import 'model_entry_adapter.dart';

/// 扫描一个模型「内置的所有动画与表情」，供「设定 → 演出」选择预览。
///
/// 数据来源按可靠性排序：
/// 1. 模型入口 `.model3.json` 的 `FileReferences.Motions / Expressions`
///    —— 带动作组名，可精确点播；
/// 2. 本机模型目录里递归扫到的 `.motion3.json` / `.exp3.json`
///    —— 自动发现，但没有组名，只列元数据；
/// 3. assets 内置模型用自带的 `resources.json` 清单（asset 不是文件系统，
///    dart:io 列不了目录；新增资源补一行清单即可，见 MODEL_ASSETS.md）。
///
/// 内存纪律：
/// * 动画文件动辄几千行 Curves，**只读开头 512 字节**取 Meta.Duration / Loop，
///   绝不把整份 motion3.json 读进内存；
/// * 结果按 model id 有界缓存（64 动作 / 64 表情），切模型才重扫；
/// * 目录遍历有 4000 条目上限，避免扫到大目录卡死设置页。
class ModelResources {
  ModelResources._();

  static const int maxMotions = 64;
  static const int maxExpressions = 64;
  static const int maxEntriesVisited = 4000;
  static const int _metaHeadBytes = 512;
  /// 每个 bundle 最多 128 条元数据，切模型频繁时缓存也要有界（LRU 8 个）。
  static const int maxCachedModels = 8;

  static final Map<String, ModelResourceBundle> _cache =
      <String, ModelResourceBundle>{};

  static String _cacheKey(ModelConfig cfg) =>
      '${cfg.id}#${ModelPath.canonicalPath(cfg.path)}';

  static void invalidate([String? modelId]) {
    if (modelId == null) {
      _cache.clear();
    } else {
      _cache.removeWhere((String k, ModelResourceBundle _) =>
          k == modelId || k.startsWith('$modelId#'));
    }
  }

  /// 最近一次扫描结果（设置页 / 单测可读）。
  static ModelResourceBundle? lastResult;

  static ModelResourceBundle _done(ModelResourceBundle bundle) {
    lastResult = bundle;
    return bundle;
  }

  static Future<ModelResourceBundle> scan(
    ModelConfig cfg, {
    AssetBundle? bundle,
  }) async {
    final String cacheKey = _cacheKey(cfg);
    final ModelResourceBundle? cached = _cache[cacheKey];
    if (cached != null) {
      _cache.remove(cacheKey);
      _cache[cacheKey] = cached;
      return _done(cached);
    }
    if (cfg.path.isEmpty) {
      return _done(const ModelResourceBundle(
        <ModelMotion>[],
        <ModelExpression>[],
        note: '尚未选择模型 · 请到「设定 → 模型」选一个模型或目录',
      ));
    }

    final bool asset = cfg.isAsset;
    final String dir = ModelPath.dirName(cfg.path);
    final String root = asset ? dir : (dir.isEmpty ? cfg.path : dir);
    // 只在 assets 分支才取 rootBundle：本机目录模型的纯 Dart 单测没有
    // 初始化 ServicesBinding，提前访问 rootBundle 会抛异常。
    final AssetBundle? assetBundle = asset ? (bundle ?? rootBundle) : null;

    // ---- 1. 入口 JSON 里声明的动作 / 表情（可点播） ----
    // 纯 .moc3 / VTS 包没有入口，适配层生成的兼容入口才是真正的声明来源。
    String entryPath = ModelPath.normalize(cfg.path);
    if (!asset && !entryPath.toLowerCase().endsWith('.json')) {
      try {
        final AdaptedEntry adapted = await ModelEntryAdapter.resolve(cfg);
        if (adapted.ok && adapted.generatedPath.isNotEmpty) {
          entryPath = adapted.generatedPath;
        }
      } catch (_) {}
    }
    String? entrySource;
    try {
      if (asset) {
        entrySource = await assetBundle!.loadString(entryPath);
      } else if (entryPath.toLowerCase().endsWith('.json')) {
        final File f = File(entryPath);
        if (await f.exists()) entrySource = await f.readAsString();
      }
    } catch (_) {
      entrySource = null;
    }

    final Map<String, ModelMotion> declared =
        <String, ModelMotion>{};
    final Map<String, ModelExpression> declaredExp =
        <String, ModelExpression>{};
    bool entryFound = false;
    if (entrySource != null && entrySource.trim().startsWith('{')) {
      final Map<String, List<Map<String, dynamic>>> groups =
          ModelPath.parseMotionGroups(entrySource);
      final List<Map<String, dynamic>> expressions =
          ModelPath.parseExpressions(entrySource);
      entryFound = groups.isNotEmpty || expressions.isNotEmpty;
      for (final MapEntry<String, List<Map<String, dynamic>>> e
          in groups.entries) {
        for (final Map<String, dynamic> m in e.value) {
          if (declared.length >= maxMotions) break;
          final String file = ModelPath.normalize(
            (m['File'] ?? '').toString(),
          );
          if (file.isEmpty) continue;
          final String name = (m['Name'] ?? '').toString().isNotEmpty
              ? (m['Name'] ?? '').toString()
              : ModelPath.modelTitle(file);
          declared[file] = ModelMotion(
            id: 'declared-$file',
            name: name,
            group: e.key,
            file: file,
            sound: ModelPath.normalize((m['Sound'] ?? '').toString()),
            declared: true,
          );
        }
      }
      for (final Map<String, dynamic> e in expressions) {
        if (declaredExp.length >= maxExpressions) break;
        final String file = ModelPath.normalize(
          (e['File'] ?? '').toString(),
        );
        if (file.isEmpty) continue;
        declaredExp[file] = ModelExpression(
          id: 'declared-$file',
          name: (e['Name'] ?? '').toString().isNotEmpty
              ? (e['Name'] ?? '').toString()
              : ModelPath.modelTitle(file),
          file: file,
          declared: true,
        );
      }
    }

    // ---- 2. 目录 / assets 清单里发现的原始资源文件 ----
    final List<String> relMotionFiles = <String>[];
    final List<String> relExpressionFiles = <String>[];
    String discoveryNote = '';
    if (asset) {
      final List<String> rels = await _assetRelPaths(assetBundle!, root);
      for (final String rel in rels) {
        if (ModelPath.isMotionFile(rel)) {
          relMotionFiles.add(rel);
        } else if (ModelPath.isExpressionFile(rel)) {
          relExpressionFiles.add(rel);
        }
      }
      if (rels.isEmpty) {
        discoveryNote = 'assets 资源清单 resources.json 不可读';
      }
    } else {
      final List<String> rels = await _localRelPaths(root);
      for (final String rel in rels) {
        if (ModelPath.isMotionFile(rel)) {
          relMotionFiles.add(rel);
        } else if (ModelPath.isExpressionFile(rel)) {
          relExpressionFiles.add(rel);
        }
      }
    }

    // ---- 3. 合并：入口声明优先，目录文件补充 ----
    final Map<String, ModelMotion> motions =
        <String, ModelMotion>{}..addAll(declared);
    for (final String rel in relMotionFiles) {
      if (motions.length >= maxMotions) break;
      final String key = ModelPath.normalize(rel);
      if (motions.containsKey(key)) continue;
      // 入口里用 ./ 或不同大小写前缀时也算同一份资源。
      final String bare = key.replaceFirst(RegExp(r'^\./'), '');
      if (motions.keys.any((String k) =>
          k.replaceFirst(RegExp(r'^\./'), '') == bare)) {
        continue;
      }
      motions[key] = ModelMotion(
        id: 'file-$key',
        name: ModelPath.modelTitle(key),
        file: key,
        declared: false,
      );
    }

    final Map<String, ModelExpression> expressions =
        <String, ModelExpression>{}..addAll(declaredExp);
    for (final String rel in relExpressionFiles) {
      if (expressions.length >= maxExpressions) break;
      final String key = ModelPath.normalize(rel);
      if (expressions.containsKey(key)) continue;
      final String bare = key.replaceFirst(RegExp(r'^\./'), '');
      if (expressions.keys.any((String k) =>
          k.replaceFirst(RegExp(r'^\./'), '') == bare)) {
        continue;
      }
      expressions[key] = ModelExpression(
        id: 'file-$key',
        name: ModelPath.modelTitle(key),
        file: key,
        declared: false,
      );
    }

    // ---- 4. 只读取动画文件头部拿时长，不载入曲线 ----
    final List<ModelMotion> motionList = <ModelMotion>[];
    for (final ModelMotion m in motions.values) {
      final (double?, bool?) meta =
          await _readMeta(asset, root, m.file, assetBundle);
      motionList.add(ModelMotion(
        id: m.id,
        name: m.name,
        group: m.group,
        file: m.file,
        sound: m.sound,
        durationSec: meta.$1,
        loop: meta.$2,
        declared: m.declared,
      ));
      if (motionList.length >= maxMotions) break;
    }
    motionList.sort((ModelMotion a, ModelMotion b) =>
        a.name.compareTo(b.name));
    final List<ModelExpression> expList =
        expressions.values.take(maxExpressions).toList()
          ..sort((ModelExpression a, ModelExpression b) =>
              a.name.compareTo(b.name));

    final List<String> notes = <String>[];
    if (!entryFound) {
      notes.add('未读到模型入口的动作组声明，以下为目录里直接扫到的资源；'
          '补齐 .model3.json 的 FileReferences.Motions 后即可按组精确点播');
    }
    if (discoveryNote.isNotEmpty) notes.add(discoveryNote);
    if (motionList.isEmpty && expList.isEmpty) {
      notes.add('没有找到任何 .motion3.json / .exp3.json · 请重试扫描或换目录');
    }

    final ModelResourceBundle result = ModelResourceBundle(
      motionList,
      expList,
      root: root,
      note: notes.join(' · '),
      entryFound: entryFound,
    );
    _cache[cacheKey] = result;
    while (_cache.length > maxCachedModels) {
      _cache.remove(_cache.keys.first);
    }
    return _done(result);
  }

  /// assets 目录列不出来，用仓库自带的 resources.json 清单。
  /// 清单里是相对模型目录的路径（中文文件名原样，不做 Uri 编码）。
  static Future<List<String>> _assetRelPaths(
    AssetBundle bundle,
    String assetDir,
  ) async {
    if (assetDir.isEmpty) return <String>[];
    try {
      final String raw =
          await bundle.loadString('$assetDir/resources.json');
      final dynamic decoded = json.decode(raw);
      if (decoded is! Map) return <String>[];
      final List<String> out = <String>[];
      for (final String key in <String>['motions', 'expressions']) {
        final dynamic list = decoded[key];
        if (list is List) {
          for (final dynamic e in list) {
            if (e is String) {
              out.add(ModelPath.normalize(e).replaceFirst(RegExp(r'^\./'), ''));
            }
          }
        }
      }
      return out.take(maxEntriesVisited).toList();
    } catch (_) {
      return <String>[];
    }
  }

  /// 本机目录：递归但有上限，返回相对模型目录的路径。
  static Future<List<String>> _localRelPaths(String root) async {
    final List<String> out = <String>[];
    if (root.isEmpty) return out;
    final Directory dir = Directory(root);
    if (!await dir.exists()) return out;
    int visited = 0;
    try {
      await for (final FileSystemEntity entity
          in dir.list(recursive: true, followLinks: false)) {
        if (visited++ >= maxEntriesVisited || out.length >= maxMotions * 2) {
          break;
        }
        if (entity is! File) continue;
        final String p = ModelPath.normalize(entity.path);
        if (!ModelPath.isMotionFile(p) && !ModelPath.isExpressionFile(p)) {
          continue;
        }
        final String prefix = ModelPath.normalize(root);
        out.add(p.startsWith('$prefix/')
            ? p.substring(prefix.length + 1)
            : p);
      }
    } catch (_) {
      // 某个子目录无权限：保留已扫到的部分。
    }
    return out;
  }

  /// 只读文件开头，解析 Meta.Duration / Meta.Loop；失败静默返回 null。
  static Future<(double?, bool?)> _readMeta(
    bool asset,
    String root,
    String rel,
    AssetBundle? bundle,
  ) async {
    final String full = root.isEmpty ? rel : '$root/$rel';
    try {
      Uint8List bytes = Uint8List(0);
      if (asset) {
        final AssetBundle? ab = bundle;
        if (ab == null) return (null, null);
        final ByteData data = await ab.load(full);
        bytes = data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes);
      } else {
        final File f = File(full);
        if (!await f.exists()) return (null, null);
        final RandomAccessFile raf = await f.open();
        try {
          final int len = await raf.length();
          final int n = len < _metaHeadBytes ? len : _metaHeadBytes;
          bytes = await raf.read(n);
        } finally {
          await raf.close();
        }
      }
      if (bytes.isEmpty) return (null, null);
      final int n = bytes.length < _metaHeadBytes ? bytes.length : _metaHeadBytes;
      final String head = utf8.decode(
        Uint8List.sublistView(bytes, 0, n),
        allowMalformed: true,
      );
      return (ModelPath.parseDuration(head), ModelPath.parseLoop(head));
    } catch (_) {
      return (null, null);
    }
  }
}
