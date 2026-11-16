import 'package:flutter/services.dart';

/// 系统目录选择结果：只关联路径 / URI，不复制任何模型文件。
class DirectoryPickResult {
  const DirectoryPickResult({
    required this.path,
    required this.uri,
    required this.display,
    required this.files,
    this.note = '',
  });

  /// 可枚举的真实文件路径（Android primary 存储 / iOS security-scoped URL.path）。
  final String path;
  /// 系统返回的 URI（权限关联用，持久化的是它而不是复制出来的副本）。
  final String uri;
  final String display;
  /// 原生侧顺手列好的模型文件（绝对路径或 content:// 伪路径）。
  final List<String> files;
  final String note;

  bool get usable => path.isNotEmpty || files.isNotEmpty;
}

/// 调用系统底层目录选择器（不新增任何 pub 依赖）：
/// Android：ACTION_OPEN_DOCUMENT_TREE（SAF，takePersistableUriPermission）
/// iOS：UIDocumentPickerViewController(.folder)，security-scoped bookmark
/// 选完只把路径 / URI / 已列出的模型文件回传，模型本体留在原目录。
class DirectoryPickerChannel {
  DirectoryPickerChannel._();

  static const MethodChannel _method =
      MethodChannel('ar_live2d_agent/directory_picker');

  static Future<DirectoryPickResult?> pick() async {
    try {
      final Map<dynamic, dynamic>? raw =
          await _method.invokeMethod<Map<dynamic, dynamic>>('pick');
      if (raw == null) return null; // 用户取消
      return DirectoryPickResult(
        path: (raw['path'] ?? '').toString(),
        uri: (raw['uri'] ?? '').toString(),
        display: (raw['display'] ?? '').toString(),
        files: (raw['files'] as List<dynamic>? ?? <dynamic>[])
            .map((dynamic e) => e.toString())
            .where((String s) => s.isNotEmpty)
            .toList(growable: false),
        note: (raw['note'] ?? '').toString(),
      );
    } on MissingPluginException {
      return DirectoryPickResult(
        path: '', uri: '', display: '', files: const <String>[],
        note: '此平台未实现系统目录选择器，请手动粘贴目录路径',
      );
    } on PlatformException catch (e) {
      return DirectoryPickResult(
        path: '', uri: '', display: '', files: const <String>[],
        note: '目录选择失败：${e.message ?? e.code} · 请重试',
      );
    }
  }
}
