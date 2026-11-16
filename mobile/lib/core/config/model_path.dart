import 'dart:convert';
import 'dart:io';

/// 模型路径与资源引用预检（纯 Dart，不依赖 Flutter / Live2D 插件）。
///
/// 修复「写着模型已就绪，但模型不显示」的第一道闸：
/// 原来 `assets/` 一律放行、绝对文件只查入口存在，插件内部静默失败后
/// UI 仍然报「已就绪」。现在在调用插件之前，把入口 JSON 里
/// FileReferences 列出的 .moc3 / 纹理 / 动作 / 表情逐个核对一遍，
/// 缺什么就明确告诉用户缺什么。
class ModelPath {
  ModelPath._();

  /// 会被当作模型 / 演出资源后缀去掉的扩展名（顺序：长的优先）。
  static const List<String> modelExtensions = <String>[
    '.model3.json',
    '.model.json',
    '.motion3.json',
    '.exp3.json',
    '.moc3',
  ];

  /// 目录模型自动探测的头像文件名（放在模型入口同目录即可）。
  static const List<String> avatarCandidates = <String>[
    'avatar.png',
    'avatar.jpg',
    'avatar.jpeg',
    'avatar.webp',
    'preview.png',
    'preview.jpg',
    'preview.webp',
    'thumbnail.png',
    'thumb.png',
    'thumb.jpg',
    'icon.png',
    '头像.png',
    '头像.jpg',
    '封面.png',
    '预览.png',
    '缩略图.png',
  ];

  static const List<String> _imageExtensions = <String>[
    '.png',
    '.jpg',
    '.jpeg',
    '.webp',
  ];

  static bool isAssetPath(String path) => normalize(path).startsWith('assets/');

  static bool isAbsolutePath(String path) {
    final String p = normalize(path);
    return p.startsWith('/') ||
        p.contains('://') ||
        RegExp(r'^[A-Za-z]:/').hasMatch(p);
  }

  static bool isMotionFile(String path) =>
      normalize(path).toLowerCase().endsWith('.motion3.json');

  static bool isExpressionFile(String path) =>
      normalize(path).toLowerCase().endsWith('.exp3.json');

  /// 去掉模型 / 演出资源扩展名，得到展示名；`.model3.json` 这种空名兜底。
  static String modelTitle(String fileNameOrPath) {
    String base = fileName(fileNameOrPath);
    for (final String e in modelExtensions) {
      if (base.toLowerCase().endsWith(e)) {
        base = base.substring(0, base.length - e.length);
        break;
      }
    }
    return base.isEmpty ? '未命名模型' : base;
  }

  /// 头像最终路径：相对路径按模型入口所在目录拼好，空串保持空。
  static String resolveAvatar(String modelPath, String avatarPath) {
    final String a = normalize(avatarPath).trim();
    if (a.isEmpty) return '';
    if (isAssetPath(a) || isAbsolutePath(a)) return a;
    final String dir = dirName(modelPath);
    return dir.isEmpty ? a : '$dir/$a';
  }

  /// 目录模型：在入口同目录探测常见头像文件，返回可直接用的绝对路径。
  /// assets / URI / 不存在目录一律返回 null（由组件层回退 name 占位）。
  static String? detectAvatar(String modelPath) {
    if (modelPath.isEmpty || isAssetPath(modelPath) || modelPath.contains('://')) {
      return null;
    }
    final String dir = dirName(modelPath);
    if (dir.isEmpty) return null;
    final String base = modelTitle(fileName(modelPath));
    final List<String> names = <String>[
      ...avatarCandidates,
      for (final String ext in _imageExtensions) '$base$ext',
    ];
    for (final String name in names) {
      try {
        final String p = join(dir, name);
        if (File(p).existsSync()) return p;
      } catch (_) {
        return null;
      }
    }
    return null;
  }

  /// 从入口 JSON 里抽 Motion 组 → 每个动作的原始 Map（供演出资源页点播）。
  static Map<String, List<Map<String, dynamic>>> parseMotionGroups(
    String source,
  ) {
    final Map<String, List<Map<String, dynamic>>> out =
        <String, List<Map<String, dynamic>>>{};
    try {
      final dynamic root = json.decode(source);
      if (root is! Map) return out;
      final dynamic refs = root['FileReferences'];
      if (refs is! Map) return out;
      final dynamic motions = refs['Motions'];
      if (motions is! Map) return out;
      for (final MapEntry<dynamic, dynamic> e in motions.entries) {
        final String group = e.key.toString();
        final List<Map<String, dynamic>> items = <Map<String, dynamic>>[];
        final dynamic list = e.value;
        if (list is List) {
          for (final dynamic m in list) {
            if (m is Map) {
              items.add(Map<String, dynamic>.from(m));
            }
          }
        }
        if (items.isNotEmpty) out[group] = items;
      }
    } catch (_) {
      return <String, List<Map<String, dynamic>>>{};
    }
    return out;
  }

  /// 从入口 JSON 里抽 Expressions 列表。
  static List<Map<String, dynamic>> parseExpressions(String source) {
    final List<Map<String, dynamic>> out = <Map<String, dynamic>>[];
    try {
      final dynamic root = json.decode(source);
      if (root is! Map) return out;
      final dynamic refs = root['FileReferences'];
      if (refs is! Map) return out;
      final dynamic list = refs['Expressions'];
      if (list is List) {
        for (final dynamic e in list) {
          if (e is Map) out.add(Map<String, dynamic>.from(e));
        }
      }
    } catch (_) {
      return <Map<String, dynamic>>[];
    }
    return out;
  }

  /// 只解析动画文件开头的 Meta，不把几千行 Curves 读进内存。
  /// 传入文件前若干字节即可（512B 足够覆盖 Meta 段）。
  static double? parseDuration(String head) {
    final Match? m = RegExp(r'"Duration"\s*:\s*([0-9]+(?:\.[0-9]+)?)')
        .firstMatch(head);
    if (m == null) return null;
    return double.tryParse(m.group(1)!);
  }

  static bool? parseLoop(String head) {
    final Match? m =
        RegExp(r'"Loop"\s*:\s*(true|false)').firstMatch(head);
    if (m == null) return null;
    return m.group(1) == 'true';
  }

  static String normalize(String path) => path.replaceAll('\\', '/');

  static String dirName(String path) {
    final String p = normalize(path);
    return p.contains('/') ? p.substring(0, p.lastIndexOf('/')) : '';
  }

  static String fileName(String path) {
    final String p = normalize(path);
    return p.contains('/') ? p.substring(p.lastIndexOf('/') + 1) : p;
  }

  /// 把 model3.json 里的相对引用拼到入口所在目录；拒绝越出目录的引用。
  static String join(String dir, String ref) {
    final String r = normalize(ref).replaceFirst(RegExp(r'^\./'), '');
    if (r.startsWith('/') || r.startsWith('assets/') || r.contains('://')) {
      return r;
    }
    return dir.isEmpty ? r : '$dir/$r';
  }

  /// 从 Cubism 入口 JSON 抽出所有被引用的文件（去重、保持顺序）。
  /// 解析失败返回空列表，由 checkLocal / materialize 给出可读原因。
  static List<String> parseReferences(String source) {
    final List<String> out = <String>[];
    final Set<String> seen = <String>{};

    void add(dynamic v) {
      if (v is! String) return;
      final String s = normalize(v).trim();
      if (s.isEmpty || s.contains('://') || seen.contains(s)) return;
      seen.add(s);
      out.add(s);
    }

    void addFileList(dynamic v) {
      if (v is List) {
        for (final dynamic e in v) {
          if (e is Map) {
            add(e['File']);
            add(e['Sound']);
          } else {
            add(e);
          }
        }
      } else if (v is Map) {
        for (final dynamic e in v.values) {
          addFileList(e);
        }
      }
    }

    try {
      final dynamic root = json.decode(source);
      if (root is! Map) return out;
      final dynamic rawRefs = root['FileReferences'];
      final Map<String, dynamic> refs = rawRefs is Map
          ? Map<String, dynamic>.from(rawRefs)
          : <String, dynamic>{};
      add(refs['Moc']);
      addFileList(refs['Textures']);
      add(refs['Physics']);
      add(refs['Pose']);
      add(refs['DisplayInfo']);
      add(refs['UserData']);
      addFileList(refs['Expressions']);
      addFileList(refs['Motions']);
    } catch (_) {
      return <String>[];
    }
    return out;
  }

  /// 同步预检：返回 null 表示可以继续，否则返回给用户的「请重试」原因。
  static String? validate(String path) {
    if (path.isEmpty) return '未选择模型 · 请到「设定 → 模型」选模型或选择目录';
    if (path.startsWith('content://') || path.startsWith('file://')) {
      return '这是系统目录 URI，不是可直接读取的文件路径 · 请重试：'
          '换内部存储目录、或手动粘贴绝对路径';
    }
    if (path.startsWith('assets/')) {
      // 内置资源由 ModelAssetInstaller 做「入口 + 引用」完整自检并物化到磁盘。
      return null;
    }
    try {
      if (!File(path).existsSync()) {
        return '模型文件不存在：$path · 请重试或重新选择目录';
      }
    } catch (_) {
      return '无法访问模型文件：$path · 请重试';
    }
    return null;
  }

  /// 绝对路径模型：核对入口 JSON 的依赖文件是否都在同一目录树内。
  static String? checkLocal(String entryPath) {
    final File entry = File(entryPath);
    if (!entry.existsSync()) {
      return '模型文件不存在：$entryPath · 请重试或重新选择目录';
    }
    if (entryPath.toLowerCase().endsWith('.moc3')) return null;
    try {
      final String source = entry.readAsStringSync();
      if (source.trim().isEmpty || !source.trim().startsWith('{')) {
        return '模型入口不是有效的 model3.json / model.json · 请检查文件';
      }
      final List<String> refs = parseReferences(source);
      if (refs.isEmpty) {
        return '模型入口缺少 FileReferences 资源清单 · '
            '请把 .moc3 / 纹理与入口放进同一目录';
      }
      final String dir = dirName(entryPath);
      final List<String> missing = <String>[];
      for (final String ref in refs) {
        final String p = join(dir, ref);
        if (!File(p).existsSync()) missing.add(ref);
      }
      if (missing.isNotEmpty) {
        final String sample = missing.take(3).join('、');
        return '模型缺少 ${missing.length} 个资源文件（$sample'
            '${missing.length > 3 ? '…' : ''}）· '
            '请把 .moc3 / 纹理 / 动作 / 表情与入口放进同一目录';
      }
      return null;
    } catch (e) {
      return '模型入口读取失败：$e · 请重试';
    }
  }
}
