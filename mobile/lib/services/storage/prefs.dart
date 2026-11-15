import 'package:shared_preferences/shared_preferences.dart';

import '../../core/config/app_config.dart';

/// 本地持久化：只在设置变更/启动时读写，禁止每帧访问（S7.5）。
class Prefs {
  Prefs._();

  static const String _kLastWsUrl = 'last_ws_url';
  static const String _kModelId = 'active_model_id';
  static const String _kQuality = 'quality';
  static const String _kCamera = 'camera_enabled';
  static const String _kAutoAsr = 'auto_send_asr';
  static const String _kName = 'character_name';

  static Future<String?> getLastWsUrl() async =>
      (await SharedPreferences.getInstance()).getString(_kLastWsUrl);

  static Future<void> setLastWsUrl(String url) async =>
      (await SharedPreferences.getInstance()).setString(_kLastWsUrl, url);

  static Future<void> loadAll() async {
    final SharedPreferences p = await SharedPreferences.getInstance();
    AppConfig.activeModelId = p.getString(_kModelId) ?? AppConfig.activeModelId;
    AppConfig.quality = StageQuality.values[p.getInt(_kQuality) ?? 1];
    AppConfig.cameraEnabled = p.getBool(_kCamera) ?? AppConfig.cameraEnabled;
    AppConfig.autoSendAsr = p.getBool(_kAutoAsr) ?? AppConfig.autoSendAsr;
    AppConfig.characterName = p.getString(_kName) ?? AppConfig.characterName;
    AppConfig.wsUrl = p.getString(_kLastWsUrl) ?? AppConfig.wsUrl;
  }

  static Future<void> saveAll() async {
    final SharedPreferences p = await SharedPreferences.getInstance();
    await p.setString(_kModelId, AppConfig.activeModelId);
    await p.setInt(_kQuality, AppConfig.quality.index);
    await p.setBool(_kCamera, AppConfig.cameraEnabled);
    await p.setBool(_kAutoAsr, AppConfig.autoSendAsr);
    await p.setString(_kName, AppConfig.characterName);
  }
}
