import 'package:flutter/material.dart';

import '../../app/gal_palette.dart';
import '../../app/stage_session.dart';
import '../../core/config/app_config.dart';
import '../../services/platform/permissions.dart';
import '../../services/platform/system_asr_channel.dart';
import '../../services/storage/prefs.dart';
import '../common/retry_hint.dart';
import '../common/section_card.dart';

/// 语音识别分区：没有电脑端时也能用系统内置转文字。
class AsrSetting extends StatefulWidget {
  const AsrSetting({super.key, required this.session});

  final StageSession session;

  @override
  State<AsrSetting> createState() => _AsrSettingState();
}

class _AsrSettingState extends State<AsrSetting> {
  String _availability = '';

  Future<void> _commit() async {
    Prefs.scheduleSave();
    widget.session.applyParams();
  }

  Future<void> _check() async {
    final bool ok = await SystemAsrChannel.available();
    if (!mounted) return;
    setState(() => _availability = ok ? '系统内置识别可用' : '系统内置识别不可用，请重试或改用服务端识别');
  }

  @override
  Widget build(BuildContext context) {
    final StageSession session = widget.session;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        SectionCard(
          title: '语音识别来源',
          children: <Widget>[
            Text(
              '离线 / 没有电脑端时，可自动改用系统内置语音识别；'
              '识别结果同样进入台词与历史，联网后按设置发送。',
              style: TextStyle(
                color: GalPalette.of(context).textDim,
                fontSize: 11,
              ),
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 6,
              children: <Widget>[
                for (final AsrMode m in AsrMode.values)
                  ChoiceChip(
                    label: Text(
                      _label(m),
                      style: TextStyle(
                        fontSize: 11,
                        color: AppConfig.asrMode == m
                            ? GalPalette.of(context).scaffold
                            : GalPalette.of(context).textDim,
                      ),
                    ),
                    selected: AppConfig.asrMode == m,
                    selectedColor: GalPalette.of(context).accent,
                    backgroundColor: GalPalette.of(context).card,
                    side: BorderSide(color: GalPalette.of(context).borderSoft),
                    onSelected: (_) async {
                      setState(() => AppConfig.asrMode = m);
                      await _commit();
                    },
                  ),
              ],
            ),
            const SizedBox(height: 10),
            AnimatedBuilder(
              animation: session,
              builder: (_, _) => Text(
                '当前生效：${session.asrEngineLabel}',
                style: TextStyle(
                  color: GalPalette.of(context).accent,
                  fontSize: 11,
                ),
              ),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: <Widget>[
                TextButton.icon(
                  onPressed: _check,
                  icon: const Icon(Icons.hearing, size: 14),
                  label: const Text('检测系统识别', style: TextStyle(fontSize: 11)),
                ),
                TextButton.icon(
                  onPressed: () async {
                    await Permissions.microphone();
                    await Permissions.speech();
                    if (mounted) setState(() {});
                  },
                  icon: const Icon(Icons.security, size: 14),
                  label: const Text(
                    '申请麦克风 / 识别权限',
                    style: TextStyle(fontSize: 11),
                  ),
                ),
              ],
            ),
            if (_availability.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                  _availability,
                  style: TextStyle(
                    color: _availability.contains('可用')
                        ? GalPalette.of(context).online
                        : GalPalette.of(context).offline,
                    fontSize: 11,
                  ),
                ),
              ),
          ],
        ),
        SectionCard(
          title: '发送与镜像',
          children: <Widget>[
            _switch(
              context,
              '语音识别后自动发送（在线时）',
              AppConfig.autoSendAsr,
              (bool v) => AppConfig.autoSendAsr = v,
            ),
            _switch(
              context,
              'ASR 文本镜像到电脑端（自动发送关时生效）',
              AppConfig.mirrorAsrText,
              (bool v) => AppConfig.mirrorAsrText = v,
            ),
            _switch(
              context,
              '打字实时镜像到电脑端（chat 已转发，默认关避免重复）',
              AppConfig.mirrorTextInput,
              (bool v) => AppConfig.mirrorTextInput = v,
            ),
          ],
        ),
        SectionCard(
          title: '离线使用说明',
          children: <Widget>[
            Text(
              '· 扫码页点「跳过」进入离线单机；\n'
              '· 语音按钮点一下开始、再点一下停止，也支持按住说话；\n'
              '· 离线识别结果会留在台词与历史里，连接后点「请重试」即可补发；\n'
              '· 系统识别不可用时会自动提示，改用服务端识别或重试。',
              style: TextStyle(
                color: GalPalette.of(context).textDim,
                fontSize: 11,
              ),
            ),
            const SizedBox(height: 10),
            RetryHint(
              compact: true,
              title: '没有电脑端？',
              detail: '把识别来源设为「系统内置」或保持「自动」，即可离线语音转文字。',
              actionLabel: '请重试检测',
              onRetry: _check,
            ),
          ],
        ),
      ],
    );
  }

  Widget _switch(
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
      onChanged: (bool v) async {
        onChanged(v);
        setState(() {});
        await _commit();
      },
    );
  }

  static String _label(AsrMode m) {
    switch (m) {
      case AsrMode.auto:
        return '自动（离线回退系统）';
      case AsrMode.server:
        return '服务端识别';
      case AsrMode.system:
        return '系统内置识别';
    }
  }
}
