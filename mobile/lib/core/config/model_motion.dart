/// 模型演出资源：动作 / 表情的轻量元数据（纯 Dart，不依赖 Flutter）。
///
/// 只存文件名、组名与时长，不缓存 motion3.json 里动辄几千行的 Curves，
/// 避免「预览列表」把整份动画曲线都读进内存。
class ModelMotion {
  const ModelMotion({
    required this.id,
    required this.name,
    this.group = '',
    this.file = '',
    this.sound = '',
    this.durationSec,
    this.loop,
    this.declared = false,
  });

  final String id;
  final String name;
  /// Cubism 动作组名（如 Idle / Tap）。插件 startMotion 只认组名。
  final String group;
  /// 资源相对路径（相对模型入口所在目录）。
  final String file;
  final String sound;
  final double? durationSec;
  final bool? loop;
  /// 是否由 .model3.json 的 FileReferences.Motions 声明（可精确点播）。
  /// 仅从目录扫到的 .motion3.json 没有组名，只能列出元数据。
  final bool declared;

  bool get playable => declared && group.isNotEmpty;

  String get durationLabel => durationSec == null
      ? '时长未知'
      : '${durationSec!.toStringAsFixed(1)}s${loop == true ? ' · 循环' : ''}';
}

class ModelExpression {
  const ModelExpression({
    required this.id,
    required this.name,
    this.file = '',
    this.declared = false,
  });

  final String id;
  final String name;
  final String file;
  final bool declared;
}

/// 一次扫描的结果：有界、可缓存、带可读提示。
class ModelResourceBundle {
  const ModelResourceBundle(
    this.motions,
    this.expressions, {
    this.root = '',
    this.note = '',
    this.entryFound = false,
  });

  final List<ModelMotion> motions;
  final List<ModelExpression> expressions;
  final String root;
  final String note;
  /// 是否读到并解析了模型入口 JSON（没有入口时只能列目录文件）。
  final bool entryFound;

  bool get isEmpty => motions.isEmpty && expressions.isEmpty;
  int get playableCount =>
      motions.where((ModelMotion m) => m.playable).length;
}
