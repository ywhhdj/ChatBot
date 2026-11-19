import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';

import '../../core/config/model_config.dart';
import '../../core/config/model_path.dart';

/// 一次过滤的结果：保留的模型 + 被跳过的条目数 + 可展示的原因。
class CatalogFilterResult {
  const CatalogFilterResult(
    this.models, {
    this.skipped = 0,
    this.notes = const <String>[],
  });

  final List<ModelConfig> models;
  final int skipped;
  final List<String> notes;

  String get note => notes.join(' · ');
  bool get hasSkipped => skipped > 0;
}

/// 模型身份识别 / 去重 / 应用私有目录过滤。
///
/// Bug 2 的根因有三层，这里一次解决：
/// 1. 同一个 Cubism 模型目录里常常同时有 `a.model3.json` 和 `a.moc3`，
///    旧扫描把它们当成两个模型 → 选中 `.moc3` 插件不解析，选中另一个又加载一次；
/// 2. 应用自己物化到文档目录 / 插件解压到 temp 的模型，会被手填路径再扫一遍，
///    和内置模型重复出现；
/// 3. `ModelConfig.all` 只按 id 去重，路径规范化后相同文件、或内置模型的
///    sdcard 副本仍会各占一张预览卡。
class ModelIdentity {
  ModelIdentity._();

  static const int _headBytes = 64 * 1024;
  static const int _maxEntryBytes = 2 * 1024 * 1024;

  /// 统一小写：Android 共享存储大小写不敏感，重复加载比误合并更常见。
  static String canonical(String path) =>
      ModelPath.canonicalPath(path).toLowerCase();

  /// 应用自己的目录（文档 / 支持 / 临时 / 外部私有），用于过滤扫描结果。
  static Future<List<String>> appRoots() async {
    final List<String> roots = <String>[];
    Future<void> add(Future<Directory> Function() getter) async {
      try {
        roots.add(canonical((await getter()).path));
      } catch (_) {}
    }

    await add(getApplicationDocumentsDirectory);
    await add(getApplicationSupportDirectory);
    await add(getTemporaryDirectory);
    try {
      final Directory? ext = await getExternalStorageDirectory();
      if (ext != null) roots.add(canonical(ext.path));
    } catch (_) {}
    return roots;
  }

  /// 是否落在应用自己的包 / 私有目录 / 插件临时解压目录里。
  /// 注意：应用文档目录**根目录**是允许放用户模型的（「用应用目录」按钮），
  /// 只排除它下面由 App 自己物化 / 生成的子目录，避免误伤。
  static bool isAppOwned(String path, List<String> roots) {
    if (ModelPath.isAppOwnedPath(path)) return true;
    final String c = canonical(path);
    const List<String> ownedSubdirs = <String>[
      '/live2d',
      '/model_adapter',
      '/flutter_live2d',
      '/compat',
    ];
    for (final String r in roots) {
      if (r.isEmpty || !(c == r || c.startsWith('$r/'))) continue;
      // 临时 / 缓存目录整体是 App 自己的产物。
      if (r.endsWith('/cache') ||
          r.endsWith('/tmp') ||
          r.contains('/library/caches')) {
        return true;
      }
      for (final String sub in ownedSubdirs) {
        if (c == '$r$sub' || c.startsWith('$r$sub/')) return true;
      }
    }
    return c.contains('/flutter_live2d/') ||
        c.contains('/model_adapter/') ||
        c.contains('/live2d/compat/');
  }

  /// 轻量「模型身份」：展示名 + .moc3 文件名 + .moc3 字节数。
  /// 同一套模型换个目录（内置包 / sdcard 副本 / 物化副本）也能判重，
  /// 只读入口头部和一次 stat，不把动作曲线或纹理读进内存。
  static String identityOf(String entryPath) {
    final String dir = ModelPath.dirName(entryPath);
    final String stem =
        ModelPath.modelTitle(ModelPath.fileName(entryPath)).toLowerCase();
    String moc = '';
    if (entryPath.toLowerCase().endsWith('.moc3')) {
      moc = ModelPath.fileName(entryPath);
    } else {
      try {
        final File f = File(entryPath);
        if (f.existsSync()) {
          final int len = f.lengthSync();
          if (len <= _maxEntryBytes) {
            final ModelEntryDoc doc =
                ModelPath.parseEntry(f.readAsStringSync());
            moc = doc.moc;
          } else {
            final RandomAccessFile raf = f.openSync();
            try {
              final int n = len < _headBytes ? len : _headBytes;
              final String head = utf8.decode(raf.readSync(n),
                  allowMalformed: true);
              moc = ModelPath.parseEntry(head).moc;
            } finally {
              raf.closeSync();
            }
          }
        }
      } catch (_) {}
    }
    if (moc.isEmpty) {
      try {
        for (final FileSystemEntity e
            in Directory(dir).listSync(followLinks: false)) {
          if (e is File && e.path.toLowerCase().endsWith('.moc3')) {
            moc = ModelPath.fileName(e.path);
            break;
          }
        }
      } catch (_) {}
    }
    String size = '';
    if (moc.isNotEmpty) {
      try {
        size = File(ModelPath.join(dir, moc)).lengthSync().toString();
      } catch (_) {}
    }
    // 读不到 .moc3 时把目录纳入身份：否则同名、不同目录的两个残缺模型
    // 会被误判成同一套，反而漏掉用户真正放进去的模型。
    if (moc.isEmpty) return '$stem||${canonical(dir)}';
    return '$stem|$moc|$size';
  }

  static int _priority(String path) {
    final String lower = ModelPath.fileName(path).toLowerCase();
    if (lower.endsWith('.model3.json')) return 4;
    if (lower.endsWith('.model.json')) return 3;
    if (lower.endsWith('.moc3')) return 2;
    if (lower.endsWith('.json')) return 1;
    return 0;
  }

  /// 过滤 + 合并，返回可直接注册进 ModelConfig.catalog 的清单。
  static CatalogFilterResult filterAndDedupe(
    List<ModelConfig> items, {
    List<String> roots = const <String>[],
    List<ModelConfig> builtIns = const <ModelConfig>[],
  }) {
    final Set<String> builtInKeys = <String>{};
    for (final ModelConfig m in builtIns) {
      if (m.path.isEmpty) continue;
      final String key = identityOf(m.path);
      // 内置入口在本地文件系统读不到（assets 是相对路径）时身份会退化成
      // `stem||dir`；拿它去匹配会误伤同名目录模型，只在拿到 .moc3 时判重。
      if (!key.contains('||')) builtInKeys.add(key);
    }

    final Map<String, int> reasonCounts = <String, int>{};
    int skipped = 0;
    void count(String reason) {
      skipped++;
      reasonCounts[reason] = (reasonCounts[reason] ?? 0) + 1;
    }

    final Map<String, ModelConfig> byIdentity = <String, ModelConfig>{};
    final Set<String> seenPaths = <String>{};

    for (final ModelConfig m in items) {
      final String path = m.path;
      if (ModelPath.isGeneratedEntry(path)) {
        count('适配层生成的兼容入口');
        continue;
      }
      if (path.contains('://')) {
        count('系统 URI（content://）不可直接加载');
        continue;
      }
      if (isAppOwned(path, roots)) {
        count('应用自身包 / 已物化副本');
        continue;
      }
      final String canon = canonical(path);
      if (!seenPaths.add(canon)) {
        count('同一路径重复条目');
        continue;
      }
      final String key = identityOf(path);
      if (builtInKeys.contains(key)) {
        count('与内置模型重复');
        continue;
      }
      final ModelConfig? existing = byIdentity[key];
      if (existing != null) {
        // 同模型多入口：优先保留标准 .model3.json。
        if (_priority(path) > _priority(existing.path)) {
          byIdentity[key] = m;
        }
        count('同模型多入口已合并');
        continue;
      }
      byIdentity[key] = m;
    }

    final List<String> notes = <String>[];
    if (skipped > 0) {
      final List<String> reasons = reasonCounts.entries
          .map((MapEntry<String, int> e) => '${e.key}×${e.value}')
          .toList();
      notes.add('已过滤 $skipped 个重复 / 不可加载条目（${reasons.join('、')}）');
    }
    final List<ModelConfig> models = byIdentity.values.toList();
    models.sort((ModelConfig a, ModelConfig b) => a.name.compareTo(b.name));
    return CatalogFilterResult(models, skipped: skipped, notes: notes);
  }
}
