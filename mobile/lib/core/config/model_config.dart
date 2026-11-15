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
      id: 'hiyori',
      name: 'Hiyori',
      path: 'assets/live2d/Deepseek/Deepseek.model3.json',
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

  static ModelConfig byId(String id) {
    for (final ModelConfig m in available) {
      if (m.id == id) return m;
    }
    return fallback;
  }
}
