import 'package:flutter/material.dart';

import '../../app/gal_palette.dart';
import '../../app/stage_session.dart';
import '../../core/config/app_config.dart';
import '../../core/config/model_config.dart';
import '../../services/live2d/model_asset_installer.dart';
import '../../services/storage/prefs.dart';
import '../common/model_avatar.dart';
import '../common/retry_hint.dart';
import '../common/section_card.dart';

/// 存储与维护：把「有多少数据、清什么、哪里没准备好」摊开给用户看。
/// 蓝色 galgame 卡片风格与其它分区一致，不新增任何依赖。
class StorageSetting extends StatefulWidget {
  const StorageSetting({super.key, required this.session});

  final StageSession session;

  @override
  State<StorageSetting> createState() => _StorageSettingState();
}

class _StorageSettingState extends State<StorageSetting> {
  bool _busy = false;
  String _note = '';

  Future<void> _clearHistory() async {
    widget.session.clearHistory();
    await Prefs.flush();
    if (mounted) setState(() => _note = '对话历史已清空并落盘');
  }

  Future<void> _rescan() async {
    if (_busy) return;
    setState(() => _busy = true);
    await widget.session.reloadModel(rescanAssets: true);
    final ModelInstallResult? probe = ModelAssetInstaller.lastResult;
    if (mounted) {
      setState(() {
        _busy = false;
        _note = probe == null
            ? '已重新自检：当前是用户目录模型，由目录预检负责'
            : (probe.ok ? '内置模型资源自检通过' : '自检发现缺失资源，见上方清单');
      });
    }
  }

  Future<void> _restore() async {
    if (_busy) return;
    setState(() => _busy = true);
    AppConfig.restoreDefaults();
    await Prefs.saveAll();
    widget.session.applyParams();
    if (mounted) {
      setState(() {
        _busy = false;
        _note = '可调参数已恢复默认 · 连接 / 身份 / 色系 / 模型目录保留';
      });
    }
  }

  Widget _row(BuildContext context, String label, String value) {
    final GalPaletteData p = GalPalette.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          SizedBox(
            width: 92,
            child: Text(label,
                style: TextStyle(color: p.textDim, fontSize: 11)),
          ),
          Expanded(
            child: Text(value,
                style: TextStyle(color: p.text, fontSize: 11)),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final GalPaletteData p = GalPalette.of(context);
    final StageSession session = widget.session;
    final ModelInstallResult? probe = ModelAssetInstaller.lastResult;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        SectionCard(
          title: '本机存储',
          children: <Widget>[
            Row(
              children: <Widget>[
                ModelAvatar(
                  model: AppConfig.activeModel,
                  size: 34,
                  radius: 8,
                  fontSize: 17,
                ),
                const SizedBox(width: 9),
                Expanded(
                  child: Text(
                    '当前模型：${AppConfig.activeModel.name}',
                    style: TextStyle(color: p.accent, fontSize: 12),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            _row(context, '对话历史',
                '${session.history.length} / ${AppConfig.maxHistoryItems} 条 · 自动保存在本机'),
            _row(context, '模型清单',
                '${ModelConfig.all.length} 条 · 目录扫描结果只存内存，不复制模型文件'),
            _row(context, '偏好设置',
                '启动时一次读入内存 · 变更去重后落盘 · 退出补写'),
            const SizedBox(height: 4),
            Text(
              '模型文件始终留在你选择的目录里；内置 assets 模型会按需复制到'
              '应用文档目录一次，供原生插件读取。',
              style: TextStyle(color: p.textFaint, fontSize: 10, height: 1.5),
            ),
          ],
        ),
        if (probe != null && !probe.ok) ...<Widget>[
          RetryHint(
            compact: true,
            title: '内置模型资源未齐',
            detail: probe.missing.isEmpty
                ? probe.error
                : '${probe.error}\n缺失：${probe.missing.take(6).join('、')}'
                    '${probe.missing.length > 6 ? '…' : ''}',
            actionLabel: '重新自检',
            onRetry: _rescan,
          ),
          const SizedBox(height: 12),
        ],
        SectionCard(
          title: '维护',
          children: <Widget>[
            Wrap(
              spacing: 8,
              runSpacing: 6,
              children: <Widget>[
                ElevatedButton.icon(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: p.cardAlt,
                    foregroundColor: p.accent,
                    padding: const EdgeInsets.symmetric(
                      horizontal: 14,
                      vertical: 8,
                    ),
                  ),
                  onPressed: _busy ? null : _rescan,
                  icon: const Icon(Icons.fact_check_outlined, size: 15),
                  label: Text(
                    _busy ? '处理中…' : '重新自检模型资源',
                    style: const TextStyle(fontSize: 12),
                  ),
                ),
                TextButton.icon(
                  onPressed: _busy ? null : _clearHistory,
                  icon: const Icon(Icons.delete_outline, size: 14),
                  label: const Text('清空对话历史', style: TextStyle(fontSize: 11)),
                ),
                TextButton.icon(
                  onPressed: _busy ? null : _restore,
                  icon: const Icon(Icons.restore, size: 14),
                  label: const Text('恢复默认参数', style: TextStyle(fontSize: 11)),
                ),
              ],
            ),
            if (_note.isNotEmpty) ...<Widget>[
              const SizedBox(height: 10),
              Text(_note,
                  style: TextStyle(color: p.online, fontSize: 11)),
            ],
          ],
        ),
      ],
    );
  }
}
