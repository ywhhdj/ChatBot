import 'dart:convert';
import 'dart:io';

/// 模型路径与资源引用预检（纯 Dart，不依赖 Flutter / Live2D 插件）。
///
/// 本轮「拓宽解析」：flutter_live2d 的原生 Core 只吃标准 Cubism 3/4/5 的
/// `.model3.json`，但用户目录里常见的是 VTube Studio 导出包、旧版
/// `.model.json`（根层字段）、带 BOM / 注释 / 尾逗号的 JSON、大小写不同的键、
/// percent-encoded 的中文路径，甚至只有一个 `.moc3`。
/// 这里把「读懂各种入口」和「生成插件能解析的标准入口」拆成纯 Dart 层：
/// * [parseEntry] 容错解析出一个 [ModelEntryDoc]；
/// * [ModelEntryDoc.toSource] 输出标准 `FileReferences` 结构；
/// * services/live2d/model_entry_adapter.dart 负责把结果写成兼容入口文件。
/// 依赖不变、插件二进制不动，等价于在插件前面加了一层解析适配。
class ModelPath {
  ModelPath._();

  /// 单个入口 JSON 允许引用的资源上限（防止坏文件把内存/IO 打满）。
  static const int maxReferences = 1024;

  /// 会被当作模型 / 演出资源后缀去掉的扩展名（顺序：长的优先）。
  static const List<String> modelExtensions = <String>[
    '.model3.json',
    '.model.json',
    '.motion3.json',
    '.exp3.json',
    '.moc3',
  ];

  /// 可交给插件的入口后缀。`.json` 需要内容探测（见 ModelCatalog）。
  static const Set<String> entryExtensions = <String>{
    '.model3.json',
    '.model.json',
    '.moc3',
    '.json',
  };

  /// 明确不是模型入口的 JSON（动作 / 表情 / 物理 / VTS 配置等）。
  static const Set<String> nonEntryExtensions = <String>{
    '.motion3.json',
    '.exp3.json',
    '.physics3.json',
    '.pose3.json',
    '.userdata3.json',
    '.displayinfo3.json',
    '.vbridger',
  };

  /// 适配层生成的兼容入口前缀：扫描时必须排除，避免「自己扫到自己」重复加载。
  static const String generatedEntryPrefix = '__gal_compat_';

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

  /// 入口文件识别：大小写不敏感；排除动作/表情等资源 JSON 与生成的兼容入口。
  /// `.json` 只按名字无法判断，调用方（ModelCatalog）需再做内容探测。
  static bool isModelFileName(String name) {
    final String lower = fileName(name).toLowerCase();
    if (lower.isEmpty || lower.startsWith('.') ||
        lower.startsWith(generatedEntryPrefix)) {
      return false;
    }
    for (final String e in nonEntryExtensions) {
      if (lower.endsWith(e)) return false;
    }
    for (final String e in entryExtensions) {
      if (lower.endsWith(e)) return true;
    }
    return false;
  }

  static bool isGeneratedEntry(String path) =>
      fileName(path).toLowerCase().startsWith(generatedEntryPrefix);

  /// 纯字符串规则：应用自己的包 / 私有目录（精确的运行时目录由
  /// ModelIdentity.appRoots() 补充）。core 层不能依赖 path_provider。
  static bool isAppOwnedPath(String path) {
    final String p = normalize(path).toLowerCase();
    const List<String> markers = <String>[
      '/android/data/',
      '/data/user/0/',
      '/data/data/',
      '/data/app/',
      '/var/mobile/containers/data/application/',
      '/library/application support/',
      'com.example.ar_live2d_agent',
    ];
    for (final String m in markers) {
      if (p.contains(m)) return true;
    }
    return false;
  }

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

  // ---------------------------------------------------------------------------
  // 容错 JSON 解析
  // ---------------------------------------------------------------------------

  /// 去掉 BOM、`//` / `/* */` 注释与尾逗号；只在非字符串状态下处理，
  /// 不会误伤中文文件名 / 路径里的 `//` 和逗号。
  static String cleanJson(String raw) {
    String s = raw;
    bool modified = false;
    if (s.startsWith('\uFEFF')) {
      s = s.substring(1);
      modified = true;
    }
    final List<String> out = <String>[];
    bool inString = false;
    bool escaped = false;
    bool lineComment = false;
    bool blockComment = false;
    for (int i = 0; i < s.length; i++) {
      final String c = s[i];
      if (lineComment) {
        if (c == '\n' || c == '\r') {
          lineComment = false;
          out.add(c);
        }
        continue;
      }
      if (blockComment) {
        if (c == '*' && i + 1 < s.length && s[i + 1] == '/') {
          blockComment = false;
          i++;
        }
        continue;
      }
      if (inString) {
        out.add(c);
        if (escaped) {
          escaped = false;
        } else if (c == '\\') {
          escaped = true;
        } else if (c == '"') {
          inString = false;
        }
        continue;
      }
      if (c == '"') {
        inString = true;
        out.add(c);
        continue;
      }
      if (c == '/' && i + 1 < s.length) {
        final String n = s[i + 1];
        if (n == '/') {
          lineComment = true;
          i++;
          modified = true;
          continue;
        }
        if (n == '*') {
          blockComment = true;
          i++;
          modified = true;
          continue;
        }
      }
      // 尾逗号只在字符串外的 `,}` / `,]` 前删除，不碰字符串内容与普通空白。
      if (c == '}' || c == ']') {
        int j = out.length - 1;
        while (j >= 0 && _isWhitespace(out[j])) {
          j--;
        }
        if (j >= 0 && out[j] == ',') {
          while (out.length > j + 1) {
            out.removeLast();
          }
          out.removeLast(); // 删掉 ','
          modified = true;
        }
      }
      out.add(c);
    }
    // 标准 JSON 原样返回：否则「需要改写」会被误判，白白生成兼容入口。
    return modified ? out.join() : s;
  }

  static bool _isWhitespace(String c) =>
      c == ' ' || c == '\n' || c == '\r' || c == '\t';

  static ({Map<String, dynamic>? map, bool dirty}) _decodeEntry(String source) {
    try {
      final String cleaned = cleanJson(source);
      final dynamic v = json.decode(cleaned);
      if (v is! Map) return (map: null, dirty: true);
      return (map: Map<String, dynamic>.from(v), dirty: cleaned != source);
    } catch (_) {
      return (map: null, dirty: true);
    }
  }

  /// 大小写不敏感取字段。
  static dynamic _field(Map<String, dynamic> m, List<String> names) {
    for (final String n in names) {
      if (m.containsKey(n)) return m[n];
    }
    final Map<String, dynamic> lowered = <String, dynamic>{
      for (final MapEntry<String, dynamic> e in m.entries)
        e.key.toLowerCase(): e.value,
    };
    for (final String n in names) {
      if (lowered.containsKey(n.toLowerCase())) return lowered[n.toLowerCase()];
    }
    return null;
  }

  static dynamic _pick(
    Map<String, dynamic> refs,
    Map<String, dynamic> root,
    List<String> names,
  ) {
    final dynamic fromRefs = _field(refs, names);
    if (fromRefs != null) return fromRefs;
    return _field(root, names);
  }

  /// 引用值规范化：去 `./`、`file://`、percent-encoding、Windows 分隔符。
  /// 绝对 / 越界 / URI 引用一律丢弃（交给调用方明确报错，不假装能加载）。
  static String normalizeRef(String value) {
    String s = normalize(value).trim();
    if (s.startsWith('file://')) s = s.substring(7);
    if (s.startsWith('./')) s = s.substring(2);
    if (s.contains('%')) {
      try {
        s = Uri.decodeFull(s);
      } catch (_) {}
    }
    if (s.isEmpty || s.contains('://') || s.startsWith('/') ||
        s.startsWith('../') || s.contains('/../') || s == '..') {
      return '';
    }
    return s;
  }

  static String _ref(dynamic v) {
    if (v is String) return normalizeRef(v);
    if (v is Map) {
      final dynamic f = _field(Map<String, dynamic>.from(v),
          <String>['File', 'file', 'Path', 'path', 'Url', 'url']);
      return f == null ? '' : _ref(f);
    }
    return '';
  }

  static List<String> _refList(dynamic v) {
    final List<String> out = <String>[];
    if (v is String) {
      final String r = _ref(v);
      if (r.isNotEmpty) out.add(r);
    } else if (v is List) {
      for (final dynamic e in v) {
        final String r = _ref(e);
        if (r.isNotEmpty) out.add(r);
      }
    } else if (v is Map) {
      for (final dynamic e in v.values) {
        out.addAll(_refList(e));
      }
    }
    return out;
  }

  static Map<String, dynamic> _motionMap(Map<dynamic, dynamic> raw) {
    final Map<String, dynamic> m = Map<String, dynamic>.from(raw);
    final dynamic file = _field(m, <String>['File', 'file', 'Path', 'path']);
    final dynamic name = _field(m, <String>['Name', 'name']);
    final dynamic sound = _field(m, <String>['Sound', 'sound']);
    final Map<String, dynamic> out = <String, dynamic>{};
    if (file != null) {
      final String f = _ref(file);
      if (f.isNotEmpty) out['File'] = f;
    }
    if (name != null && name.toString().isNotEmpty) {
      out['Name'] = name.toString();
    }
    if (sound != null) {
      final String s = _ref(sound);
      if (s.isNotEmpty) out['Sound'] = s;
    }
    return out;
  }

  /// 把一个（可能很不标准的）入口 JSON 读成统一结构。
  /// 坏 JSON 返回带 warning 的空 doc，绝不抛异常。
  static ModelEntryDoc parseEntry(String source) {
    final ({Map<String, dynamic>? map, bool dirty}) decoded =
        _decodeEntry(source);
    final Map<String, dynamic>? root = decoded.map;
    if (root == null) {
      return const ModelEntryDoc(
        warnings: <String>['入口不是有效 JSON'],
        needsRewrite: true,
      );
    }
    bool dirty = decoded.dirty;
    final List<String> warnings = <String>[];
    if (dirty) warnings.add('入口含 BOM / 注释 / 尾逗号，已规范化');

    final dynamic rawRefs = _field(
        root, <String>['FileReferences', 'file_references', 'references']);
    final bool hasRefs = rawRefs is Map;
    final Map<String, dynamic> refs = hasRefs
        ? Map<String, dynamic>.from(rawRefs)
        : <String, dynamic>{};
    if (!hasRefs) {
      dirty = true;
      warnings.add('入口使用根层字段（旧版 model.json 风格），已转成 FileReferences');
    }

    final dynamic rawMoc = _pick(refs, root,
        <String>['Moc', 'moc', 'Model', 'model']);
    String moc = _ref(rawMoc);
    final dynamic rawTextures = _pick(refs, root,
        <String>['Textures', 'textures']);
    final List<String> textures = _refList(rawTextures);
    if (rawTextures is Map || rawTextures is String) dirty = true;

    final String physics = _ref(_pick(
        refs, root, <String>['Physics', 'physics']));
    final String pose =
        _ref(_pick(refs, root, <String>['Pose', 'pose']));
    final String displayInfo = _ref(_pick(
        refs, root, <String>['DisplayInfo', 'displayInfo', 'displayinfo']));
    final String userData = _ref(_pick(
        refs, root, <String>['UserData', 'userData', 'userdata']));

    // ---- Motions ----
    final Map<String, List<Map<String, dynamic>>> motions =
        <String, List<Map<String, dynamic>>>{};
    final dynamic rawMotions = _pick(refs, root,
        <String>['Motions', 'motions', 'Motion', 'motion']);
    if (rawMotions is Map) {
      for (final MapEntry<dynamic, dynamic> e
          in (rawMotions).entries) {
        final String group = e.key.toString();
        final List<Map<String, dynamic>> items = <Map<String, dynamic>>[];
        final dynamic list = e.value;
        if (list is List) {
          for (final dynamic m in list) {
            if (m is Map) items.add(_motionMap(m));
          }
        } else if (list is Map) {
          dirty = true;
          items.add(_motionMap(list));
        } else if (list is String) {
          dirty = true;
          items.add(<String, dynamic>{'File': _ref(list)});
        }
        final List<Map<String, dynamic>> clean = items
            .where((Map<String, dynamic> m) => m.containsKey('File'))
            .take(maxReferences)
            .toList();
        if (clean.isNotEmpty) motions[group] = clean;
      }
    } else if (rawMotions is List || rawMotions is String) {
      dirty = true;
      warnings.add('Motions 不是动作组映射，已归入 Idle 组');
      final List<Map<String, dynamic>> items = <Map<String, dynamic>>[];
      final List<dynamic> list =
          rawMotions is List ? rawMotions : <dynamic>[rawMotions];
      for (final dynamic m in list) {
        if (m is Map) {
          items.add(_motionMap(m));
        } else {
          final String f = _ref(m);
          if (f.isNotEmpty) items.add(<String, dynamic>{'File': f});
        }
      }
      final List<Map<String, dynamic>> clean = items
          .where((Map<String, dynamic> m) => m.containsKey('File'))
          .take(maxReferences)
          .toList();
      if (clean.isNotEmpty) motions['Idle'] = clean;
    }

    // ---- Expressions ----
    final dynamic rawExp = _pick(refs, root,
        <String>['Expressions', 'expressions']);
    final List<dynamic> expList = <dynamic>[];
    if (rawExp is List) {
      expList.addAll(rawExp);
    } else if (rawExp is Map) {
      dirty = true;
      warnings.add('Expressions 是映射，已展平成列表');
      expList.addAll(rawExp.values);
    } else if (rawExp is String) {
      dirty = true;
      expList.add(rawExp);
    }
    final List<Map<String, dynamic>> exps = <Map<String, dynamic>>[];
    for (final dynamic e in expList) {
      if (exps.length >= maxReferences) break;
      if (e is Map) {
        final Map<String, dynamic> m = _motionMap(e);
        if (m.containsKey('File')) exps.add(m);
      } else {
        final String f = _ref(e);
        if (f.isNotEmpty) {
          exps.add(<String, dynamic>{'File': f});
        }
      }
    }

    int version = 3;
    final dynamic rawVersion = _field(root, <String>['Version', 'version']);
    if (rawVersion is num) version = rawVersion.toInt();
    if (moc.toLowerCase().endsWith('.moc')) {
      // Cubism 2 的二进制 .moc 不是 .moc3，插件内置的 Cubism Core 解析不了。
      warnings.add('检测到 Cubism 2 的 .moc；请用 Cubism 3+ 重新导出 .moc3');
      return ModelEntryDoc(
        version: version,
        moc: moc,
        textures: textures,
        physics: physics,
        pose: pose,
        displayInfo: displayInfo,
        userData: userData,
        motions: motions,
        expressions: exps,
        warnings: warnings,
        needsRewrite: true,
        unsupported: 'Cubism 2 的 .moc 无法由内置 Cubism Core 解析，'
            '请用 Cubism 3+ 重新导出 .moc3 后再加载',
      );
    }
    if (moc.isEmpty && hasRefs) {
      dirty = true;
      warnings.add('入口没有声明 Moc，适配层会从目录里自动推断 .moc3');
    }
    if (version < 3) {
      dirty = true;
      version = 3;
    }

    return ModelEntryDoc(
      version: version,
      moc: moc,
      textures: textures,
      physics: physics,
      pose: pose,
      displayInfo: displayInfo,
      userData: userData,
      motions: motions,
      expressions: exps,
      warnings: warnings,
      needsRewrite: dirty,
    );
  }

  /// 从入口 JSON 里抽 Motion 组 → 每个动作的原始 Map（供演出资源页点播）。
  static Map<String, List<Map<String, dynamic>>> parseMotionGroups(
    String source,
  ) => parseEntry(source).motions;

  /// 从入口 JSON 里抽 Expressions 列表。
  static List<Map<String, dynamic>> parseExpressions(String source) =>
      parseEntry(source).expressions;

  /// 从 Cubism 入口 JSON 抽出所有被引用的文件（去重、保持顺序、有上限）。
  static List<String> parseReferences(String source) =>
      parseEntry(source).references;

  /// 只解析动画文件开头的 Meta，不把几千行 Curves 读进内存。
  static double? parseDuration(String head) {
    final Match? m = RegExp(
      r'"Duration"\s*:\s*"?([0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)"?',
      caseSensitive: false,
    ).firstMatch(head);
    if (m == null) return null;
    return double.tryParse(m.group(1)!);
  }

  static bool? parseLoop(String head) {
    final Match? m = RegExp(
      r'"Loop"\s*:\s*"?((?:true)|(?:false)|(?:1)|(?:0))"?',
      caseSensitive: false,
    ).firstMatch(head);
    if (m == null) return null;
    final String v = m.group(1)!.toLowerCase();
    return v == 'true' || v == '1';
  }

  static String normalize(String path) => path.replaceAll('\\', '/');

  /// 规范化成可比较的路径（去 `./`、重复斜杠、`../` 回退），不做 Uri 编码，
  /// 中文文件名保持原样。
  static String canonicalPath(String path) {
    String p = normalize(path).trim();
    if (p.startsWith('file://')) p = p.substring(7);
    final bool absolute = p.startsWith('/');
    final List<String> parts = <String>[];
    for (final String part in p.split('/')) {
      if (part.isEmpty || part == '.') continue;
      if (part == '..') {
        if (parts.isNotEmpty) parts.removeLast();
      } else {
        parts.add(part);
      }
    }
    final String joined = parts.join('/');
    if (absolute) return '/$joined';
    if (joined.isEmpty) return '';
    return joined;
  }

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

  /// 同步预检：返回 null 表示可以继续，否则返回给用户的「请重试」原因。
  static String? validate(String path) {
    if (path.isEmpty) return '未选择模型 · 请到「设定 → 模型」选模型或选择目录';
    if (path.startsWith('content://') || path.startsWith('file://')) {
      return '这是系统目录 URI，不是可直接读取的文件路径 · 请重试：'
          '换内部存储目录、或手动粘贴绝对路径';
    }
    if (path.startsWith('assets/')) {
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
  /// 保留同步版本给既有调用点 / 单测，App 内请改用 [checkLocalAsync]。
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
      return _checkRefs(entryPath, source, (String p) => File(p).existsSync());
    } catch (e) {
      return '模型入口读取失败：$e · 请重试';
    }
  }

  /// 异步版本：不再在 UI isolate 上做几百次同步 stat。
  static Future<String?> checkLocalAsync(String entryPath) async {
    final File entry = File(entryPath);
    if (!await entry.exists()) {
      return '模型文件不存在：$entryPath · 请重试或重新选择目录';
    }
    if (entryPath.toLowerCase().endsWith('.moc3')) return null;
    try {
      final String source = await entry.readAsString();
      if (source.trim().isEmpty || !source.trim().startsWith('{')) {
        return '模型入口不是有效的 model3.json / model.json · 请检查文件';
      }
      int checked = 0;
      final List<String> missing = <String>[];
      final List<String> refs = parseReferences(source);
      if (refs.isEmpty) {
        return '模型入口缺少 FileReferences 资源清单 · '
            '请把 .moc3 / 纹理与入口放进同一目录';
      }
      final String dir = dirName(entryPath);
      for (final String ref in refs) {
        if (checked++ >= maxReferences || missing.length >= 8) break;
        if (!await File(join(dir, ref)).exists()) missing.add(ref);
      }
      if (missing.isNotEmpty) {
        return _missingText(missing);
      }
      return null;
    } catch (e) {
      return '模型入口读取失败：$e · 请重试';
    }
  }

  static String? _checkRefs(
    String entryPath,
    String source,
    bool Function(String) exists,
  ) {
    final List<String> refs = parseReferences(source);
    if (refs.isEmpty) {
      return '模型入口缺少 FileReferences 资源清单 · '
          '请把 .moc3 / 纹理与入口放进同一目录';
    }
    final String dir = dirName(entryPath);
    final List<String> missing = <String>[];
    int checked = 0;
    for (final String ref in refs) {
      if (checked++ >= maxReferences || missing.length >= 8) break;
      if (!exists(join(dir, ref))) missing.add(ref);
    }
    return missing.isEmpty ? null : _missingText(missing);
  }

  static String _missingText(List<String> missing) {
    final String sample = missing.take(3).join('、');
    return '模型缺少 ${missing.length} 个资源文件（$sample'
        '${missing.length > 3 ? '…' : ''}）· '
        '请把 .moc3 / 纹理 / 动作 / 表情与入口放进同一目录';
  }
}

/// 容错解析后的统一模型入口描述（纯数据，可单测）。
class ModelEntryDoc {
  const ModelEntryDoc({
    this.version = 3,
    this.moc = '',
    this.textures = const <String>[],
    this.physics = '',
    this.pose = '',
    this.displayInfo = '',
    this.userData = '',
    this.motions = const <String, List<Map<String, dynamic>>>{},
    this.expressions = const <Map<String, dynamic>>[],
    this.warnings = const <String>[],
    this.needsRewrite = false,
    this.unsupported = '',
  });

  final int version;
  final String moc;
  final List<String> textures;
  final String physics;
  final String pose;
  final String displayInfo;
  final String userData;
  final Map<String, List<Map<String, dynamic>>> motions;
  final List<Map<String, dynamic>> expressions;
  final List<String> warnings;
  /// 源不是「干净的标准 Cubism 3 入口」，需要写成兼容副本。
  final bool needsRewrite;
  /// 非空 = 这份模型无法交给插件（如 Cubism 2 的 .moc）。
  final String unsupported;

  bool get hasReferences =>
      moc.isNotEmpty ||
      textures.isNotEmpty ||
      physics.isNotEmpty ||
      pose.isNotEmpty ||
      displayInfo.isNotEmpty ||
      userData.isNotEmpty ||
      expressions.isNotEmpty ||
      motions.isNotEmpty;

  /// 全部被引用文件（去重、有上限）。顺序与旧实现一致。
  List<String> get references {
    final List<String> out = <String>[];
    final Set<String> seen = <String>{};
    void add(String s) {
      if (s.isEmpty || seen.contains(s)) return;
      if (out.length >= ModelPath.maxReferences) return;
      seen.add(s);
      out.add(s);
    }

    add(moc);
    for (final String t in textures) {
      add(t);
    }
    add(physics);
    add(pose);
    add(displayInfo);
    add(userData);
    for (final Map<String, dynamic> e in expressions) {
      add((e['File'] ?? '').toString());
    }
    for (final List<Map<String, dynamic>> list in motions.values) {
      for (final Map<String, dynamic> m in list) {
        add((m['File'] ?? '').toString());
        add((m['Sound'] ?? '').toString());
      }
    }
    return out;
  }

  /// 输出插件能解析的标准 `.model3.json` 文本。
  String toSource() {
    final Map<String, dynamic> refs = <String, dynamic>{};
    if (moc.isNotEmpty) refs['Moc'] = moc;
    if (textures.isNotEmpty) refs['Textures'] = textures;
    if (physics.isNotEmpty) refs['Physics'] = physics;
    if (pose.isNotEmpty) refs['Pose'] = pose;
    if (displayInfo.isNotEmpty) refs['DisplayInfo'] = displayInfo;
    if (userData.isNotEmpty) refs['UserData'] = userData;
    if (expressions.isNotEmpty) {
      refs['Expressions'] = expressions
          .map((Map<String, dynamic> e) => <String, dynamic>{
                if ((e['Name'] ?? '').toString().isNotEmpty)
                  'Name': e['Name'].toString(),
                'File': (e['File'] ?? '').toString(),
              })
          .toList();
    }
    if (motions.isNotEmpty) {
      refs['Motions'] = <String, dynamic>{
        for (final MapEntry<String, List<Map<String, dynamic>>> e
            in motions.entries)
          e.key: e.value
              .map((Map<String, dynamic> m) => <String, dynamic>{
                    'File': (m['File'] ?? '').toString(),
                    if ((m['Name'] ?? '').toString().isNotEmpty)
                      'Name': m['Name'].toString(),
                    if ((m['Sound'] ?? '').toString().isNotEmpty)
                      'Sound': m['Sound'].toString(),
                  })
              .toList(),
      };
    }
    return json.encode(<String, dynamic>{
      'Version': version < 3 ? 3 : version,
      'FileReferences': refs,
    });
  }
}
