import 'package:ar_live2d_agent/app/stage_session.dart';
import 'package:flutter/material.dart';

import '../../app/routes.dart';
import '../../app/stage_scope.dart';
import '../../core/config/app_config.dart';
import '../../services/platform/permissions.dart';
import '../../services/storage/prefs.dart';
import '../common/section_card.dart';

/// 连接与输入设置（F02 / F05 / S6.4）。
class ConnectionSetting extends StatefulWidget {
  const ConnectionSetting({super.key});

  @override
  State<ConnectionSetting> createState() => _ConnectionSettingState();
}

class _ConnectionSettingState extends State<ConnectionSetting> {
  late final TextEditingController _nameController =
      TextEditingController(text: AppConfig.characterName);

  @override
  void dispose() {
    _nameController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final StageSession session = StageScope.of(context);
    return SectionCard(
      title: '连接 / 输入',
      children: <Widget>[
        Text(AppConfig.wsUrl.isEmpty ? '离线单机演出' : AppConfig.wsUrl,
            style: const TextStyle(color: Colors.white70, fontSize: 12)),
        const SizedBox(height: 8),
        Row(
          children: <Widget>[
            Expanded(
              child: SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('语音自动发送',
                    style: TextStyle(color: Colors.white70, fontSize: 12)),
                value: AppConfig.autoSendAsr,
                onChanged: (bool v) async {
                  setState(() => AppConfig.autoSendAsr = v);
                  await Prefs.saveAll();
                },
              ),
            ),
            Expanded(
              child: SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('相机预览',
                    style: TextStyle(color: Colors.white70, fontSize: 12)),
                value: AppConfig.cameraEnabled,
                onChanged: (bool v) async {
                  if (v && !await Permissions.camera()) {
                    await Permissions.openSettings();
                    return;
                  }
                  setState(() => AppConfig.cameraEnabled = v);
                  await Prefs.saveAll();
                },
              ),
            ),
          ],
        ),
        TextField(
          decoration: const InputDecoration(
            labelText: '角色名',
            labelStyle: TextStyle(color: Colors.white54, fontSize: 12),
          ),
          style: const TextStyle(color: Colors.white, fontSize: 13),
          controller: _nameController,
          onChanged: (String v) => AppConfig.characterName = v,
        ),
        const SizedBox(height: 8),
        Row(
          children: <Widget>[
            TextButton(
              onPressed: () async {
                await Prefs.saveAll();
                if (mounted) {
                  await Navigator.of(context).pushReplacementNamed(AppRoutes.stage,
                      arguments: AppConfig.wsUrl);
                }
              },
              child: const Text('保存并重连'),
            ),
            const Spacer(),
            Text('状态：${session.ws.state.name}',
                style: const TextStyle(color: Colors.white38, fontSize: 11)),
          ],
        ),
      ],
    );
  }
}
