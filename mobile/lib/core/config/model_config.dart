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
    this.custom = false,
  });

  final String id;
  final String name;
  final String path;
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
  static const List<ModelConfig> available = <ModelConfig>[
    fallback,
    ModelConfig(
      id: 'deepseek-01',
      name: 'DeepSeek',
      path: 'assets/live2d/deepseek/deepseek.model3.json',
      motionGroups: <String, String>{
        'idle': 'Idle',
        'jumpOut': 'JumpOut',
        'peekBack': 'PeekBack',
        'turnLeft': 'TurnLeft',
        'turnRight': 'TurnRight',
      },
      paramMap: defaultParamMap,
    ),
  ];

  /// 由 ModelCatalog 扫描用户目录后注入（有界，不缓存大对象）。
  static List<ModelConfig> catalog = <ModelConfig>[];

  static void registerCatalog(List<ModelConfig> items) {
    catalog = List<ModelConfig>.unmodifiable(items);
  }

  /// 当前可选清单：占位 + 内置 + 用户目录。
  static List<ModelConfig> get all => <ModelConfig>[
        ...available,
        ...catalog.where((ModelConfig m) =>
            available.every((ModelConfig a) => a.id != m.id)),
      ];

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
  String get fileName => path.isEmpty ? '' : path.split('/').last;
  String get dirName =>
      path.isEmpty || !path.contains('/') ? '' : path.substring(0, path.lastIndexOf('/'));
}
