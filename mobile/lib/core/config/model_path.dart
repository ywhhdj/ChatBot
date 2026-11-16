import 'dart:io';

/// 模型路径预检（纯 Dart，不依赖 Flutter / Live2D 插件）。
///
/// 把「文件不存在 / content:// 无法直读」这类问题在调插件之前就暴露给用户，
/// 避免插件内部静默失败导致「模型怎么都不加载」且没有任何线索。
class ModelPath {
  ModelPath._();

  /// 返回 null 表示可以尝试加载；否则返回给用户的「请重试」原因。
  static String? validate(String path) {
    if (path.isEmpty) return '未选择模型 · 请到「设定 → 模型」选模型或选择目录';
    if (path.startsWith('content://') || path.startsWith('file://')) {
      return '这是系统目录 URI，不是可直接读取的文件路径 · 请重试：'
          '换内部存储目录、或手动粘贴绝对路径';
    }
    if (path.startsWith('assets/')) {
      // 内置清单交给插件 / AssetBundle；资源缺失由 pubspec 声明与占位提示兜底。
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
}
