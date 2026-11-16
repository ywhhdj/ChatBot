import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';

import '../../core/config/model_config.dart';
import '../../core/config/model_path.dart';
import '../platform/directory_picker_channel.dart';

/// 用户自选模型目录扫描结果。
class CatalogResult {
  const CatalogResult(this.models, {this.root = '', this.error = ''});
  final List<ModelConfig> models;
  final String root;
  final String error;
  bool get ok => error.isEmpty;
}

/// 模型目录扫描（纯 Dart IO，不新增依赖）：
/// * 用户可自由填任意目录；留空则用应用文档目录；
/// * 只认 Cubism 模型入口 `.model3.json` / `.model.json` 与旧版 `.moc3`；
/// * 递归深度 2、结果上限 64 条、遍历条目上限 4000，避免扫到大目录卡死设置页；
/// * 扫描结果只保留轻量元数据，缩略预览由组件层画渐变卡，不缓存大对象。
class ModelCatalog {
  ModelCatalog._();

  static const int maxModels = 64;
  static const int maxDepth = 2;
  static const int maxEntriesVisited = 4000;
  static const Set<String> _exts = <String>{
    '.model3.json',
    '.model.json',
    '.moc3',
  };

  static bool isModelFileName(String name) {
    final String lower = name.toLowerCase();
    for (final String e in _exts) {
      if (lower.endsWith(e)) return true;
    }
    return false;
  }

  /// 展示名统一走 ModelPath.modelTitle（同时兼容动作 / 表情扩展名）。
  static String titleOf(String path) => ModelPath.modelTitle(path);

  /// 稳定 id：旧实现用 `path.hashCode.abs()`，只在**同一进程**内稳定。
  /// activeModelId 会写进 SharedPreferences，重启后 Dart String.hashCode
  /// 不保证一致，用户上次选的目录模型会被 byId 判成未知而回退占位
  /// —— 这是「模型明明选过却不加载」的隐藏根因之一。
  /// 改为对规范化路径做 base64Url 编码，跨重启、跨版本都一致。
  static String idOf(String path) {
    final String normalized = path.replaceAll('\\', '/');
    return 'dir-${base64Url.encode(utf8.encode(normalized)).replaceAll('=', '')}';
  }

  /// 旧版本 `dir-<hash>` 迁移：无法反推路径时自动落到第一个可用目录模型，
  /// 而不是静默回退占位立绘。
  static String resolveSavedId(String savedId) {
    if (ModelConfig.all.any((ModelConfig m) => m.id == savedId)) return savedId;
    if (savedId.startsWith('dir-') && ModelConfig.catalog.isNotEmpty) {
      return ModelConfig.catalog.first.id;
    }
    return ModelConfig.fallback.id;
  }

  static Future<CatalogResult> scan(String? customDir) async {
    String root = (customDir ?? '').trim();
    if (root.isEmpty) {
      try {
        root = (await getApplicationDocumentsDirectory()).path;
      } catch (_) {
        return const CatalogResult(
          <ModelConfig>[],
          error: '无法读取应用文档目录，请重试或手动填写模型目录',
        );
      }
    }
    final Directory dir = Directory(root);
    if (!await dir.exists()) {
      return CatalogResult(
        <ModelConfig>[],
        root: root,
        error: '目录不存在：$root · 请重试或换一个目录',
      );
    }

    final List<ModelConfig> found = <ModelConfig>[];
    final List<int> visited = <int>[0];
    try {
      await _walk(dir, 0, found, visited);
    } catch (e) {
      return CatalogResult(<ModelConfig>[], root: root, error: '扫描失败：$e · 请重试');
    }
    found.sort((ModelConfig a, ModelConfig b) => a.name.compareTo(b.name));
    final List<ModelConfig> bounded =
        found.length > maxModels ? found.sublist(0, maxModels) : found;
    return CatalogResult(bounded, root: root);
  }

  static Future<void> _walk(
    Directory dir,
    int depth,
    List<ModelConfig> out,
    List<int> visited,
  ) async {
    if (depth > maxDepth || out.length >= maxModels) return;
    await for (final FileSystemEntity entity in dir.list(followLinks: false)) {
      if (out.length >= maxModels || visited[0] >= maxEntriesVisited) return;
      visited[0]++;
      if (entity is File && isModelFileName(entity.path)) {
        final String path = entity.path;
        out.add(ModelConfig(
          id: idOf(path),
          name: titleOf(path),
          path: path,
          scale: 1.0,
          custom: true,
          avatarPath: ModelPath.detectAvatar(path) ?? '',
        ));
      } else if (entity is Directory && depth < maxDepth) {
        await _walk(entity, depth + 1, out, visited);
      }
    }
  }

  /// 把扫描结果注入全局可选清单，返回新的可选列表。
  static Future<List<ModelConfig>> refresh(String? customDir) async {
    final CatalogResult result = await scan(customDir);
    ModelConfig.registerCatalog(result.models);
    return ModelConfig.all;
  }

  /// 系统底层目录选择器返回的结果：只关联路径 / URI，**不复制模型文件**。
  /// 原生侧若已列出模型文件（SAF / iOS bookmark 场景）就直接用清单，
  /// 否则回退到 dart:io 扫真实路径。
  static Future<CatalogResult> fromPicked(DirectoryPickResult picked) async {
    final List<ModelConfig> items = <ModelConfig>[];
    for (final String raw in picked.files) {
      if (!isModelFileName(raw)) continue;
      items.add(ModelConfig(
        id: idOf(raw),
        name: titleOf(raw),
        path: raw,
        custom: true,
        avatarPath: ModelPath.detectAvatar(raw) ?? '',
      ));
      if (items.length >= maxModels) break;
    }
    final String root = picked.path.isNotEmpty ? picked.path : picked.uri;
    if (items.isEmpty && picked.path.isNotEmpty) {
      return scan(picked.path);
    }
    if (items.isEmpty) {
      return CatalogResult(
        <ModelConfig>[],
        root: root,
        error: picked.note.isNotEmpty
            ? picked.note
            : '该目录无法以文件路径访问：请重试选择内部存储目录，或手动粘贴绝对路径',
      );
    }
    items.sort((ModelConfig a, ModelConfig b) => a.name.compareTo(b.name));
    return CatalogResult(
      items,
      root: root,
      error: picked.path.isEmpty
          ? '已关联系统目录（URI），模型文件为 content:// 引用；'
              '若加载失败请换内部存储目录或手动粘贴绝对路径'
          : '',
    );
  }
}
