import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';

import '../../core/config/model_config.dart';
import '../../core/config/model_path.dart';
import '../platform/directory_picker_channel.dart';
import 'model_identity.dart';

/// 用户自选模型目录扫描结果。
class CatalogResult {
  const CatalogResult(
    this.models, {
    this.root = '',
    this.error = '',
    this.skipped = 0,
    this.skippedNote = '',
  });

  final List<ModelConfig> models;
  final String root;
  final String error;
  /// 被过滤掉的重复 / 不可加载条目数（可观测，避免「模型怎么少了」）。
  final int skipped;
  final String skippedNote;
  bool get ok => error.isEmpty;
}

/// 模型目录扫描（纯 Dart IO，不新增依赖）：
/// * 用户可自由填任意目录；留空则用应用文档目录；
/// * 入口识别拓宽：`.model3.json` / `.model.json` / `.moc3` / 任意 `.json`
///   （后者做内容探测，动作 / 表情 / VTS 配置不会被误当成模型）；
/// * 过滤应用自己的包 / 物化副本 / 适配层生成的兼容入口 / content:// 伪路径；
/// * 同一模型的多个入口（.model3.json + .moc3）合并成一张卡，避免重复加载；
/// * 递归深度 2、结果上限 64 条、遍历条目上限 4000，避免扫到大目录卡死设置页；
/// * 扫描结果只保留轻量元数据，缩略预览由组件层画渐变卡，不缓存大对象。
class ModelCatalog {
  ModelCatalog._();

  static const int maxModels = 64;
  static const int maxDepth = 2;
  static const int maxEntriesVisited = 4000;
  static const int _rawLimit = maxModels * 6;
  static const int _probeBytes = 8192;

  static bool isModelFileName(String name) =>
      ModelPath.isModelFileName(name);

  /// 展示名统一走 ModelPath.modelTitle（同时兼容动作 / 表情扩展名）。
  static String titleOf(String path) => ModelPath.modelTitle(path);

  /// 稳定 id：对规范化路径做 base64Url 编码，跨重启、跨版本都一致，
  /// 且能反解回路径（见 [pathFromId] / [restoreSaved]）。
  static String idOf(String path) {
    final String normalized = ModelPath.canonicalPath(path);
    return 'dir-${base64Url.encode(utf8.encode(normalized)).replaceAll('=', '')}';
  }

  /// [idOf] 的反解：用于重启后按持久化的路径恢复单个模型。
  static String pathFromId(String id) {
    if (!id.startsWith('dir-')) return '';
    final String raw = id.substring(4);
    try {
      String padded = raw.replaceAll('-', '+').replaceAll('_', '/');
      while (padded.length % 4 != 0) {
        padded += '=';
      }
      final String decoded = utf8.decode(base64.decode(padded));
      // 旧版 dir-<hash> 碰巧也可能是合法 base64，解出来是乱码 / 纯数字。
      // 只接受看起来像路径的结果，避免把垃圾串当成模型文件恢复。
      if (!decoded.contains('/') && !decoded.contains('\\')) return '';
      return decoded;
    } catch (_) {
      return '';
    }
  }

  /// 旧版本 `dir-<hash>` 迁移：无法反推路径时自动落到第一个可用目录模型，
  /// 而不是静默回退占位立绘。
  static String resolveSavedId(String savedId) {
    if (ModelConfig.all.any((ModelConfig m) => m.id == savedId)) {
      return savedId;
    }
    if (savedId.startsWith('dir-') && ModelConfig.catalog.isNotEmpty) {
      return ModelConfig.catalog.first.id;
    }
    return ModelConfig.fallback.id;
  }

  /// 重启恢复增强：当前 id 不在清单里时，先从 id 反解出路径，
  /// 若文件还在且不是 App 私有 / 生成入口，就把这一条重新注册回来，
  /// 而不是「换一个模型」或回退占位（那会让用户上次选的模型凭空消失）。
  static String restoreSaved(String savedId) {
    if (ModelConfig.all.any((ModelConfig m) => m.id == savedId)) {
      return savedId;
    }
    final String path = pathFromId(savedId);
    if (path.isEmpty ||
        path.contains('://') ||
        ModelPath.isGeneratedEntry(path) ||
        ModelPath.isAppOwnedPath(path)) {
      return resolveSavedId(savedId);
    }
    try {
      if (!File(path).existsSync()) return resolveSavedId(savedId);
    } catch (_) {
      return resolveSavedId(savedId);
    }
    final ModelConfig item = ModelConfig(
      id: savedId,
      name: titleOf(path),
      path: path,
      scale: 1.0,
      custom: true,
      avatarPath: ModelPath.detectAvatar(path) ?? '',
    );
    ModelConfig.registerCatalog(<ModelConfig>[
      ...ModelConfig.catalog,
      item,
    ]);
    return item.id;
  }

  static Future<CatalogResult> scan(String? customDir) async {
    String root = (customDir ?? '').trim();
    final List<String> roots = await ModelIdentity.appRoots();
    if (root.isNotEmpty && ModelPath.isAppOwnedPath(root)) {
      return CatalogResult(
        <ModelConfig>[],
        root: root,
        error: '这是应用自己的私有包目录，里面的模型已由内置清单 / 物化副本加载过；'
            '请改选内部存储里的模型目录，或点「用应用目录」扫描应用文档目录',
      );
    }
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
      await _walk(dir, 0, found, visited, roots);
    } catch (e) {
      return CatalogResult(<ModelConfig>[], root: root, error: '扫描失败：$e · 请重试');
    }
    final CatalogFilterResult filtered = ModelIdentity.filterAndDedupe(
      found,
      roots: roots,
      builtIns: ModelConfig.available,
    );
    final List<ModelConfig> bounded = filtered.models.length > maxModels
        ? filtered.models.sublist(0, maxModels)
        : filtered.models;
    return CatalogResult(
      bounded,
      root: root,
      skipped: filtered.skipped,
      skippedNote: filtered.note,
    );
  }

  static Future<void> _walk(
    Directory dir,
    int depth,
    List<ModelConfig> out,
    List<int> visited,
    List<String> roots,
  ) async {
    if (depth > maxDepth || out.length >= _rawLimit) return;
    late final Stream<FileSystemEntity> entities;
    try {
      entities = dir.list(followLinks: false);
    } catch (_) {
      return; // 无权限目录：跳过，保留别的目录已扫到的结果。
    }
    try {
      await for (final FileSystemEntity entity in entities) {
        if (out.length >= _rawLimit || visited[0] >= maxEntriesVisited) {
          return;
        }
        visited[0]++;
        if (entity is File) {
          final String path = entity.path;
          if (ModelPath.isGeneratedEntry(path) ||
              !isModelFileName(path) ||
              ModelIdentity.isAppOwned(path, roots)) {
            continue;
          }
          if (path.toLowerCase().endsWith('.json') &&
              !await _looksLikeEntry(entity)) {
            continue;
          }
          out.add(ModelConfig(
            id: idOf(path),
            name: titleOf(path),
            path: path,
            scale: 1.0,
            custom: true,
            avatarPath: ModelPath.detectAvatar(path) ?? '',
          ));
        } else if (entity is Directory && depth < maxDepth) {
          if (ModelIdentity.isAppOwned(entity.path, roots)) continue;
          await _walk(entity, depth + 1, out, visited, roots);
        }
      }
    } catch (_) {
      // 单个子目录遍历失败：不让它把整次扫描结果丢掉。
    }
  }

  /// 任意 `.json` 都可能是入口，也可能只是动作 / 表情 / VTS 配置。
  /// 只读开头 8KB 判断，绝不把整份资源读进内存。
  static Future<bool> _looksLikeEntry(File f) async {
    RandomAccessFile? raf;
    try {
      raf = await f.open();
      final int len = await raf.length();
      final int n = len < _probeBytes ? len : _probeBytes;
      final String head = utf8.decode(await raf.read(n), allowMalformed: true)
          .toLowerCase();
      if (head.contains('"curves"')) return false;
      return head.contains('"filereferences"') ||
          head.contains('"moc"') ||
          head.contains('"textures"') ||
          head.contains('"model"');
    } catch (_) {
      return false;
    } finally {
      try {
        await raf?.close();
      } catch (_) {}
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
    final List<String> roots = await ModelIdentity.appRoots();
    final List<ModelConfig> items = <ModelConfig>[];
    for (final String raw in picked.files) {
      if (raw.contains('://') ||
          ModelPath.isGeneratedEntry(raw) ||
          !isModelFileName(raw) ||
          ModelIdentity.isAppOwned(raw, roots)) {
        continue;
      }
      items.add(ModelConfig(
        id: idOf(raw),
        name: titleOf(raw),
        path: raw,
        custom: true,
        avatarPath: ModelPath.detectAvatar(raw) ?? '',
      ));
      if (items.length >= _rawLimit) break;
    }
    final String root = picked.path.isNotEmpty ? picked.path : picked.uri;
    if (items.isEmpty && picked.path.isNotEmpty) {
      return scan(picked.path);
    }
    final CatalogFilterResult filtered = ModelIdentity.filterAndDedupe(
      items,
      roots: roots,
      builtIns: ModelConfig.available,
    );
    final List<ModelConfig> bounded = filtered.models.length > maxModels
        ? filtered.models.sublist(0, maxModels)
        : filtered.models;
    if (bounded.isEmpty) {
      return CatalogResult(
        <ModelConfig>[],
        root: root,
        skipped: filtered.skipped,
        skippedNote: filtered.note,
        error: picked.note.isNotEmpty
            ? picked.note
            : '该目录无法以文件路径访问：请重试选择内部存储目录，或手动粘贴绝对路径',
      );
    }
    return CatalogResult(
      bounded,
      root: root,
      skipped: filtered.skipped,
      skippedNote: filtered.note,
      error: picked.path.isEmpty
          ? '已关联系统目录（URI），模型文件为 content:// 引用；'
              '若加载失败请换内部存储目录或手动粘贴绝对路径'
          : '',
    );
  }
}
