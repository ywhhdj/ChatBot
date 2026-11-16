import 'package:flutter/material.dart';

import '../../app/gal_palette.dart';
import '../../app/routes.dart';
import '../../app/stage_session.dart';
import '../../core/config/app_config.dart';
import '../../services/platform/permissions.dart';
import '../../services/storage/prefs.dart';
import '../common/section_card.dart';

/// 连接与输入设置：全屏设置页里的一个分区（不再是 bottom sheet）。
/// 离线（扫码跳过）也能在这里填地址点「重连」，或去独立页面手动输入。
class ConnectionSetting extends StatefulWidget {
  const ConnectionSetting({super.key, required this.session});

  final StageSession session;

  @override
  State<ConnectionSetting> createState() => _ConnectionSettingState();
}

class _ConnectionSettingState extends State<ConnectionSetting> {
  late final TextEditingController _nameController = TextEditingController(
    text: AppConfig.characterName,
  );
  late final TextEditingController _urlController = TextEditingController(
    text: widget.session.ws.url.isNotEmpty
        ? widget.session.ws.url
        : AppConfig.suggestedWsUrl,
  );

  @override
  void dispose() {
    _nameController.dispose();
    _urlController.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    AppConfig.characterName = _nameController.text.trim().isEmpty
        ? AppConfig.characterName
        : _nameController.text.trim();
    Prefs.scheduleSave();
    widget.session.applyParams();
    if (mounted) setState(() {});
  }

  Future<void> _reconnect() async {
    await widget.session.reconnect(_urlController.text);
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final StageSession session = widget.session;
    final String uid = AppConfig.uid.isEmpty ? '未生成' : AppConfig.uid;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        SectionCard(
          title: '串流地址',
          children: <Widget>[
            Text(
              session.ws.url.isEmpty ? '离线单机演出（可点重连）' : session.ws.url,
              style: TextStyle(
                color: GalPalette.of(context).textDim,
                fontSize: 12,
              ),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _urlController,
              keyboardType: TextInputType.url,
              style: TextStyle(
                color: GalPalette.of(context).text,
                fontSize: 12,
              ),
              decoration: InputDecoration(
                labelText: '串流地址（支持 ws://…/?uid= 或 JSON 二维码）',
                labelStyle: TextStyle(
                  color: GalPalette.of(context).textFaint,
                  fontSize: 11,
                ),
                hintText: 'ws://192.168.1.10:8000/',
                hintStyle: TextStyle(
                  color: GalPalette.of(context).textFaint,
                  fontSize: 11,
                ),
                enabledBorder: UnderlineInputBorder(
                  borderSide: BorderSide(color: GalPalette.of(context).border),
                ),
              ),
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 4,
              children: <Widget>[
                ElevatedButton.icon(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: GalPalette.of(context).cardAlt,
                    foregroundColor: GalPalette.of(context).accent,
                    padding: const EdgeInsets.symmetric(
                      horizontal: 14,
                      vertical: 8,
                    ),
                  ),
                  onPressed: _reconnect,
                  icon: const Icon(Icons.cable, size: 15),
                  label: const Text('重连', style: TextStyle(fontSize: 12)),
                ),
                TextButton.icon(
                  onPressed: () => AppRoutes.pushOnce(
                    context,
                    AppRoutes.connect,
                  ),
                  icon: const Icon(Icons.open_in_new, size: 14),
                  label: const Text('独立连接页', style: TextStyle(fontSize: 11)),
                ),
                TextButton(
                  onPressed: _save,
                  child: const Text('保存参数', style: TextStyle(fontSize: 12)),
                ),
                TextButton(
                  onPressed: () async {
                    await session.resetIdentity();
                    if (mounted) setState(() {});
                  },
                  child: const Text('重新绑定身份', style: TextStyle(fontSize: 12)),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              'uid：$uid',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: GalPalette.of(context).textFaint,
                fontSize: 10,
              ),
            ),
            AnimatedBuilder(
              animation: session,
              builder: (_, _) => Text(
                '状态：${session.ws.state.name} · '
                '${session.ws.isRegistered ? '已绑定' : '未绑定'} · '
                '${session.asrEngineLabel}',
                style: TextStyle(
                  color: GalPalette.of(context).textFaint,
                  fontSize: 10,
                ),
              ),
            ),
          ],
        ),
        SectionCard(
          title: '画面与输入',
          children: <Widget>[
            Row(
              children: <Widget>[
                Expanded(
                  child: _switchTile(context, '语音自动发送', AppConfig.autoSendAsr, (
                    bool v,
                  ) async {
                    setState(() => AppConfig.autoSendAsr = v);
                    Prefs.scheduleSave();
                  }),
                ),
                Expanded(
                  child: _switchTile(
                    context,
                    '相机实时背景',
                    AppConfig.cameraEnabled,
                    (bool v) async {
                      if (v && !await Permissions.camera()) {
                        await Permissions.openSettings();
                        return;
                      }
                      setState(() => AppConfig.cameraEnabled = v);
                      Prefs.scheduleSave();
                      // 背景层在另一棵子树里，必须让 session 通知它重建。
                      session.applyParams();
                    },
                  ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Row(
              children: <Widget>[
                Text(
                  '相机镜头：',
                  style: TextStyle(
                    color: GalPalette.of(context).textDim,
                    fontSize: 11,
                  ),
                ),
                const SizedBox(width: 6),
                for (final CameraSide side in CameraSide.values)
                  Padding(
                    padding: const EdgeInsets.only(right: 6),
                    child: ChoiceChip(
                      label: Text(
                        side == CameraSide.front ? '前置' : '后置',
                        style: TextStyle(
                          fontSize: 11,
                          color: AppConfig.cameraFacing == side
                              ? GalPalette.of(context).scaffold
                              : GalPalette.of(context).textDim,
                        ),
                      ),
                      selected: AppConfig.cameraFacing == side,
                      selectedColor: GalPalette.of(context).accent,
                      backgroundColor: GalPalette.of(context).card,
                      side: BorderSide(
                        color: GalPalette.of(context).borderSoft,
                      ),
                      onSelected: (_) async {
                        setState(() => AppConfig.cameraFacing = side);
                        Prefs.scheduleSave();
                        // 换镜头必须重建相机控制器（ValueKey 含 facing）。
                        session.applyParams();
                      },
                    ),
                  ),
              ],
            ),
            _switchTile(context, '断线自动重连', AppConfig.autoReconnect, (
              bool v,
            ) async {
              setState(() => AppConfig.autoReconnect = v);
              Prefs.scheduleSave();
            }),
            TextField(
              decoration: InputDecoration(
                labelText: '角色名',
                labelStyle: TextStyle(
                  color: GalPalette.of(context).textFaint,
                  fontSize: 12,
                ),
              ),
              style: TextStyle(
                color: GalPalette.of(context).text,
                fontSize: 13,
              ),
              controller: _nameController,
              onChanged: (String v) => AppConfig.characterName = v,
            ),
          ],
        ),
      ],
    );
  }

  Widget _switchTile(
    BuildContext context,
    String label,
    bool value,
    ValueChanged<bool> onChanged,
  ) {
    return SwitchListTile(
      contentPadding: EdgeInsets.zero,
      dense: true,
      activeColor: GalPalette.of(context).accent,
      title: Text(
        label,
        style: TextStyle(color: GalPalette.of(context).textDim, fontSize: 11),
      ),
      value: value,
      onChanged: onChanged,
    );
  }
}
