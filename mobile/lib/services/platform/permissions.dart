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

  static Future<void> openSettings() => openAppSettings();
}
