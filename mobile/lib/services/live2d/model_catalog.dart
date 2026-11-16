import 'dart:io';

import 'package:path_provider/path_provider.dart';

import '../../core/config/model_config.dart';
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
/// * 递归深度 2、结果上限 64 条，避免遍历整块存储拖慢设置页；
/// * 扫描结果只保留轻量元数据，缩略预览由组件层画渐变卡，不缓存大对象。
class ModelCatalog {
  ModelCatalog._();

  static const int maxModels = 64;
  static const int maxDepth = 2;
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

  static String _title(String path) {
    String base = path.split('/').last;
    for (final String e in _exts) {
      if (base.toLowerCase().endsWith(e)) {
        base = base.substring(0, base.length - e.length);
        break;
      }
    }
    return base.isEmpty ? '未命名模型' : base;
  }

  /// 纯函数：生成稳定的 id（同一路径多次扫描结果一致，便于持久化选中项）。
  static String idOf(String path) => 'dir-${path.hashCode.abs()}';

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
    try {
      await _walk(dir, 0, found);
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
  ) async {
    if (depth > maxDepth || out.length >= maxModels) return;
    await for (final FileSystemEntity entity in dir.list(followLinks: false)) {
      if (out.length >= maxModels) return;
      if (entity is File && isModelFileName(entity.path)) {
        final String path = entity.path;
        out.add(ModelConfig(
          id: idOf(path),
          name: _title(path),
          path: path,
          scale: 1.0,
          custom: true,
        ));
      } else if (entity is Directory && depth < maxDepth) {
        await _walk(entity, depth + 1, out);
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
        name: _title(raw),
        path: raw,
        custom: true,
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
