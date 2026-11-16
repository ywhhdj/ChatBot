import 'package:permission_handler/permission_handler.dart';

class Permissions {
  Permissions._();

  /// U26：区分 granted / limited / permanentlyDenied，UI 用 Galgame 提示行引导。
  static Future<bool> microphone() async {
    final PermissionStatus s = await Permission.microphone.request();
    return s.isGranted || s.isLimited;
  }

  static Future<bool> microphonePermanentlyDenied() async =>
      (await Permission.microphone.status).isPermanentlyDenied;

  static Future<bool> camera() async =>
      (await Permission.camera.request()).isGranted;

  /// iOS 的语音识别授权（Android 一般随 RECORD_AUDIO 一起具备）。
  static Future<bool> speech() async {
    try {
      final PermissionStatus s = await Permission.speech.request();
      return s.isGranted || s.isLimited;
    } catch (_) {
      return true; // 部分 Android 版本没有该权限项，不阻断
    }
  }

  /// Android「显示在其他应用上层」；permission_handler 会打开系统授权页。
  static Future<bool> overlay() async {
    try {
      final PermissionStatus s = await Permission.systemAlertWindow.request();
      return s.isGranted;
    } catch (_) {
      return false;
    }
  }

  static Future<void> openSettings() => openAppSettings();
}
