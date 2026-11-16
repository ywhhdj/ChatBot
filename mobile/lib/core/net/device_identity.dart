import 'dart:math';

/// 注册身份（docs/api.md §4.5.1）：uid 必须匹配 `[A-Za-z0-9._:-]{1,64}`，
/// 匿名场景用客户端持久化 UUID，重连绝不能换人。
/// 纯 Dart，不依赖 SharedPreferences / uuid 包（避免新增依赖）。
class DeviceIdentity {
  DeviceIdentity._();

  static const String mobile = 'mobile';
  static const String desktop = 'desktop';
  static const String unknown = 'unknown';

  static final RegExp _uidRe = RegExp(r'^[A-Za-z0-9._:-]{1,64}$');

  static bool isValid(String uid) => _uidRe.hasMatch(uid);

  /// 形如 `mobile-6f1c…-a3d0`，64 位以内且只含正则允许的字符。
  static String newUid([String prefix = mobile]) {
    final Random r = Random.secure();
    String block(int bytes) {
      final StringBuffer sb = StringBuffer();
      for (int i = 0; i < bytes; i++) {
        sb.write(r.nextInt(256).toRadixString(16).padLeft(2, '0'));
      }
      return sb.toString();
    }

    final String stamp = DateTime.now().microsecondsSinceEpoch.toRadixString(16);
    return '$prefix-${stamp.substring(stamp.length > 12 ? stamp.length - 12 : 0)}-'
        '${block(4)}-${block(6)}';
  }

  /// 扫码/设置里带来的 uid 合法就沿用（与电脑端配对成同一用户），否则本机新生成。
  static String normalize(String raw, [String prefix = mobile]) {
    final String t = raw.trim();
    return isValid(t) ? t : newUid(prefix);
  }
}
