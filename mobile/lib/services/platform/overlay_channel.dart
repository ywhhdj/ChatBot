import 'package:flutter/services.dart';

/// 「Live2D 模型在所有应用之上置顶」悬浮窗（Android SYSTEM_ALERT_WINDOW）。
///
/// iOS 不支持跨应用置顶，available() 返回 false，Dart 侧给出明确提示，
/// 仍保留应用内低帧率后台演出。悬浮窗里的 Live2D 渲染需要原生 Cubism/纹理桥接，
/// 当前原生侧提供一个可拖动的浮窗视图（角色名牌 + 状态），Dart 侧持续以低帧率驱动。
class OverlayChannel {
  OverlayChannel._();

  static const MethodChannel _method =
      MethodChannel('ar_live2d_agent/overlay');

  static Future<bool> available() async {
    try {
      return await _method.invokeMethod<bool>('available') ?? false;
    } on MissingPluginException {
      return false;
    } catch (_) {
      return false;
    }
  }

  static Future<bool> canDraw() async {
    try {
      return await _method.invokeMethod<bool>('canDraw') ?? false;
    } catch (_) {
      return false;
    }
  }

  static Future<bool> start(
    String modelName, {
    String scheme = 'blue',
    double scale = 0.55,
  }) async {
    try {
      return await _method.invokeMethod<bool>(
            'start',
            <String, dynamic>{
              'name': modelName,
              'scheme': scheme,
              'scale': scale,
            },
          ) ??
          false;
    } catch (_) {
      return false;
    }
  }

  /// 切换色系 / 换模型 / 改缩放时同步原生浮窗，不重建窗口。
  static Future<void> updateAppearance({
    String? name,
    String? scheme,
    double? scale,
  }) async {
    try {
      await _method.invokeMethod<void>(
        'updateAppearance',
        <String, dynamic>{
          if (name != null) 'name': name,
          if (scheme != null) 'scheme': scheme,
          if (scale != null) 'scale': scale,
        },
      );
    } catch (_) {
      // 原生侧未实现时不影响应用内演出
    }
  }

  static Future<void> stop() async {
    try {
      await _method.invokeMethod<void>('stop');
    } catch (_) {
      // 忽略：进程退出时系统会自动回收
    }
  }
}
