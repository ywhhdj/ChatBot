import 'model_path.dart';

/// 模型配置：纯数据
///
/// motionGroups / paramMap 允许为空：缺资源或缺参数能力时由组件层降级为
/// Transform 动画（见 services/live2d/live2d_stage.dart）。
class ModelConfig {
  const ModelConfig({
    required this.id,
    required this.name,
    required this.path,
    this.scale = 1.0,
    this.anchorX = 0.0,
    this.anchorY = 0.0,
    this.motionGroups = const <String, String>{},
    this.paramMap = const <String, String>{},
    this.expressions = const <String, String>{},
    this.avatarPath = '',
    this.custom = false,
  });

  final String id;
  final String name;
  final String path;
  /// 预览头像：assets 路径或本机绝对路径，空串 = 用 name 首字母占位。
  /// 有路径但加载失败时组件层同样回退占位，不会出现空白卡片。
  final String avatarPath;
  final double scale;
  final double anchorX;
  final double anchorY;
  final Map<String, String> motionGroups;
  final Map<String, String> paramMap;
  final Map<String, String> expressions;
  /// 来自用户自选目录（不是 assets 内置清单）。
  final bool custom;

  /// 常用 Live2D 参数名（仅作配置，运行时做能力探测，不猜测插件 API）。
  static const Map<String, String> defaultParamMap = <String, String>{
    'angleX': 'ParamAngleX',
    'angleY': 'ParamAngleY',
    'angleZ': 'ParamAngleZ',
    'bodyAngleX': 'ParamBodyAngleX',
  };

  /// 无模型资源时的占位立绘（path 为空 => 组件层走渐变降级）。
  static const ModelConfig fallback = ModelConfig(
    id: 'placeholder',
    name: '未设置模型',
    path: '',
  );

  /// 用户把合法模型放到 assets/live2d/ 后在此登记即可，不下载任何资源。
  /// 注意：登记 ≠ 资源已存在。入口 .model3.json / .moc3 / 纹理缺失时
  /// Live2DStage 会明确降级提示，不会再谎报「模型已就绪」。
  /// pubspec.yaml 的 assets 声明必须把每个子目录单独列出，否则子目录资源不打包。
  /// dev 分支当前只提交了 Animation/Exp3/VTS 配置，模型本体（.moc3 / 纹理 /
  /// .model3.json）需自行放入，或用「设定 → 模型」选本机目录模型。
  static const List<ModelConfig> available = <ModelConfig>[
    fallback,
    ModelConfig(
      id: 'deepseek-01',
      name: '大肥鱼',
      path: 'assets/live2d/deepseek/大肥鱼.model3.json',
      motionGroups: <String, String>{
        'idle': 'Idle',
        'jumpOut': 'JumpOut',
        'peekBack': 'PeekBack',
        'turnLeft': 'TurnLeft',
        'turnRight': 'TurnRight',
      },
      paramMap: defaultParamMap,
      avatarPath: 'assets/live2d/deepseek/大肥鱼.png',
    ),
  ];

  /// 由 ModelCatalog 扫描用户目录后注入（有界，不缓存大对象）。
  static List<ModelConfig> catalog = <ModelConfig>[];

  /// `all` 每次构造新列表 + 遍历 catalog，旧实现在 UI build 里被反复调用
  /// （状态栏 / 设定页 / 头像卡），属于白扔的分配。缓存到下次注册时失效。
  static List<ModelConfig>? _allCache;

  static void registerCatalog(List<ModelConfig> items) {
    final Set<String> seenIds = <String>{};
    final Set<String> seenPaths = <String>{};
    final List<ModelConfig> out = <ModelConfig>[];
    for (final ModelConfig m in items) {
      if (out.length >= 64) break;
      if (m.id.isEmpty || seenIds.contains(m.id)) continue;
      final String key = m.path.isEmpty
          ? 'id:${m.id}'
          : ModelPath.canonicalPath(m.path).toLowerCase();
      if (!seenPaths.add(key)) continue;
      seenIds.add(m.id);
      out.add(m);
    }
    catalog = List<ModelConfig>.unmodifiable(out);
    _allCache = null;
  }

  /// 当前可选清单：占位 + 内置 + 用户目录（只读缓存）。
  static List<ModelConfig> get all {
    final List<ModelConfig>? cached = _allCache;
    if (cached != null) return cached;
    final List<ModelConfig> built =
        List<ModelConfig>.unmodifiable(<ModelConfig>[
      ...available,
      ...catalog.where((ModelConfig m) =>
          available.every((ModelConfig a) => a.id != m.id)),
    ]);
    _allCache = built;
    return built;
  }

  static ModelConfig byId(String id) {
    for (final ModelConfig m in all) {
      if (m.id == id) return m;
    }
    // 旧版本残留 / 目录被删：回退占位，避免 Dropdown/列表 value 不在 items 中崩溃。
    return fallback;
  }

  /// id 是否仍在可选清单里（设定页做安全兜底）。
  static bool isValidId(String id) =>
      all.any((ModelConfig m) => m.id == id);

  /// 目录里的模型文件名（插件 loadModel 用 basename，不能把完整路径再传一遍）。
  String get fileName => ModelPath.fileName(path);
  String get dirName => ModelPath.dirName(path);

  /// 头像最终路径：相对路径按模型入口所在目录拼好，空串保持空。
  String get resolvedAvatarPath => ModelPath.resolveAvatar(path, avatarPath);

  bool get hasAvatar => resolvedAvatarPath.isNotEmpty;

  /// 是否 assets 内置路径（需要先物化到磁盘才能交给原生插件）。
  bool get isAsset => path.startsWith('assets/');

  /// 远端 model_set 可能带一个本地清单里没有的 id/path：注册为有界的临时
  /// 目录模型，避免 byId 回退占位让「电脑端换模」永远失效。
  static ModelConfig registerExternal(String id, String rawPath) {
    final String path = ModelPath.normalize(rawPath).trim();
    // 远端 model_set 以前可以塞 content:// / .txt / 应用私有目录，
    // 注册后必然加载失败还会污染 activeModelId；这里先挡一道。
    final bool usable = path.isNotEmpty &&
        !path.contains('://') &&
        !ModelPath.isAppOwnedPath(path) &&
        (ModelPath.isModelFileName(path) ||
            path.toLowerCase().endsWith('.moc3'));
    final ModelConfig item = ModelConfig(
      id: id,
      name: ModelPath.fileName(path).isEmpty
          ? '远端模型'
          : ModelPath.modelTitle(ModelPath.fileName(path)),
      path: usable ? path : '',
      custom: true,
      avatarPath: usable ? (ModelPath.detectAvatar(path) ?? '') : '',
    );
    final List<ModelConfig> next = <ModelConfig>[
      ...catalog.where((ModelConfig m) => m.id != id),
      item,
    ];
    // 有界：远端连续换模型不会把 catalog 撑成无上限列表。
    registerCatalog(next.length > 64
        ? next.sublist(next.length - 64)
        : next);
    return item;
  }
}
