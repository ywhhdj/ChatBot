import 'package:flutter/material.dart';

import '../../app/gal_palette.dart';
import '../../app/stage_session.dart';
import '../../core/config/app_config.dart';
import '../../core/config/model_config.dart';
import '../../core/config/model_motion.dart';
import '../../services/live2d/model_resources.dart';
import '../common/model_avatar.dart';
import '../common/retry_hint.dart';
import '../common/section_card.dart';

/// 演出分区：列出当前模型**内置的所有动画与表情**，让用户自由选择预览。
///
/// * 懒加载：只有第一次滑到这一页才扫描（外层 _LazySection 已保证）；
/// * 动画只读文件头部 512B 取时长，不载入几千行 Curves；
/// * 由入口 .model3.json 声明的动作带组名 → 可精确点播；
///   仅从目录扫到的文件只列元数据，并明确标注原因；
/// * 「去舞台看」= 下发演出 + 返回舞台，不用切页面找状态。
class MotionSetting extends StatefulWidget {
  const MotionSetting({super.key, required this.session});

  final StageSession session;

  @override
  State<MotionSetting> createState() => _MotionSettingState();
}

class _MotionSettingState extends State<MotionSetting> {
  ModelResourceBundle? _bundle;
  String _loadedFor = '';
  String _selectedId = '';
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    widget.session.modelRevision.addListener(_onModelChanged);
    _load();
  }

  @override
  void dispose() {
    widget.session.modelRevision.removeListener(_onModelChanged);
    super.dispose();
  }

  // 换模或「重新自检资源」后强制重扫：补齐入口 JSON / 新动作文件时，
  // 列表要能立刻反映出来，而不是被同 id 缓存挡住。
  void _onModelChanged() => _load(force: true);

  Future<void> _load({bool force = false}) async {
    final ModelConfig model = AppConfig.activeModel;
    if (!force && _loadedFor == model.id && _bundle != null) return;
    if (_loading) return;
    _loading = true;
    _loadedFor = model.id;
    if (force) ModelResources.invalidate(model.id);
    final ModelResourceBundle bundle =
        await ModelResources.scan(model);
    _loading = false;
    if (!mounted) return;
    setState(() {
      _bundle = bundle;
      _selectedId = '';
    });
  }

  Future<void> _play(ModelMotion m, {bool goStage = false}) async {
    await widget.session.playMotion(m);
    if (!mounted) return;
    setState(() => _selectedId = m.id);
    if (goStage) Navigator.of(context).maybePop();
  }

  Future<void> _playGroup(String group) async {
    await widget.session.playMotion(
      ModelMotion(id: 'group-$group', name: group, group: group, declared: true),
    );
    if (mounted) setState(() {});
  }

  Widget _info(BuildContext context, String text) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Text(
          text,
          style: TextStyle(
            color: GalPalette.of(context).textFaint,
            fontSize: 10,
            height: 1.5,
          ),
        ),
      );

  Widget _chip(
    BuildContext context,
    String label,
    Color color, {
    IconData? icon,
  }) {
    final GalPaletteData p = GalPalette.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: p.dialog.withValues(alpha: .9),
        borderRadius: BorderRadius.circular(7),
        border: Border.all(color: color.withValues(alpha: .55)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          if (icon != null) ...<Widget>[
            Icon(icon, size: 10, color: color),
            const SizedBox(width: 3),
          ],
          Text(label, style: TextStyle(color: color, fontSize: 9)),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final StageSession session = widget.session;
    final GalPaletteData p = GalPalette.of(context);
    final ModelConfig model = AppConfig.activeModel;
    final ModelResourceBundle? bundle = _bundle;
    final bool ready = session.live2d.ready;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        SectionCard(
          title: '演出资源 · 当前模型',
          children: <Widget>[
            Row(
              children: <Widget>[
                ModelAvatar(model: model, size: 44, radius: 9, fontSize: 22),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        model.name,
                        style: TextStyle(color: p.accent, fontSize: 13),
                      ),
                      const SizedBox(height: 3),
                      Text(
                        bundle == null ? '正在扫描…' : bundle.root,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          color: p.textFaint,
                          fontSize: 10,
                        ),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  icon: Icon(Icons.refresh, size: 18, color: p.accent),
                  tooltip: '重新扫描动画与表情',
                  onPressed: _loading ? null : () => _load(force: true),
                ),
              ],
            ),
            const SizedBox(height: 8),
            _info(
              context,
              '动画 ${bundle?.motions.length ?? 0} 个 · '
              '表情 ${bundle?.expressions.length ?? 0} 个 · '
              '可精确点播 ${bundle?.playableCount ?? 0} 个。'
              '有头像用头像，没有用名字首字母占位。',
            ),
            if (!ready)
              _info(
                context,
                '模型当前未就绪：资源仍可查看，但点播需要先到「模型」分区加载模型。',
              ),
          ],
        ),

        if (bundle != null && bundle.note.isNotEmpty) ...<Widget>[
          RetryHint(
            compact: true,
            title: bundle.isEmpty ? '没有找到演出资源' : '资源说明',
            detail: bundle.note,
            actionLabel: '重新扫描',
            onRetry: () => _load(force: true),
          ),
          const SizedBox(height: 12),
        ],

        if (model.motionGroups.isNotEmpty)
          SectionCard(
            title: '动作组快捷试播',
            children: <Widget>[
              _info(context, '这些是配置里登记的演出动作组，点一下即下发到舞台。'),
              Wrap(
                spacing: 8,
                runSpacing: 6,
                children: <Widget>[
                  for (final MapEntry<String, String> e
                      in model.motionGroups.entries)
                    ActionChip(
                      backgroundColor: p.card,
                      side: BorderSide(color: p.borderSoft),
                      label: Text(
                        '${e.key} → ${e.value}',
                        style: TextStyle(color: p.textDim, fontSize: 10),
                      ),
                      onPressed: () => _playGroup(e.value),
                    ),
                ],
              ),
            ],
          ),

        if (bundle != null && bundle.motions.isNotEmpty)
          SectionCard(
            title: '内置动画 · 点选预览',
            children: <Widget>[
              _info(
                context,
                '「入口声明」可精确按组点播；「目录文件」只列出元数据，'
                '需补齐 .model3.json 的 Motions 才能精确点播。点「去舞台看」'
                '会下发演出并返回舞台。',
              ),
              ListView.builder(
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                itemCount: bundle.motions.length,
                itemBuilder: (BuildContext context, int i) =>
                    _MotionTile(
                  motion: bundle.motions[i],
                  selected: bundle.motions[i].id == _selectedId,
                  onPlay: () => _play(bundle.motions[i]),
                  onGoStage: () => _play(bundle.motions[i], goStage: true),
                ),
              ),
            ],
          ),

        if (bundle != null && bundle.expressions.isNotEmpty)
          SectionCard(
            title: '内置表情（${bundle.expressions.length}）',
            children: <Widget>[
              _info(
                context,
                '表情资源已全部列出。插件当前只暴露了动作播放接口，'
                '表情需在模型内部按参数切换，这里不假装能点播。',
              ),
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: <Widget>[
                  for (final ModelExpression e in bundle.expressions)
                    _chip(
                      context,
                      e.name,
                      e.declared ? p.accentSoft : p.textFaint,
                      icon: Icons.face_retouching_natural,
                    ),
                ],
              ),
            ],
          ),

        if (bundle == null)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 24),
            child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
          ),
      ],
    );
  }
}

class _MotionTile extends StatelessWidget {
  const _MotionTile({
    required this.motion,
    required this.selected,
    required this.onPlay,
    required this.onGoStage,
  });

  final ModelMotion motion;
  final bool selected;
  final VoidCallback onPlay;
  final VoidCallback onGoStage;

  @override
  Widget build(BuildContext context) {
    final GalPaletteData p = GalPalette.of(context);
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        color: p.card.withValues(alpha: .85),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: selected ? p.accent : p.borderSoft,
          width: selected ? 1.5 : 1,
        ),
      ),
      child: ListTile(
        dense: true,
        contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 2),
        leading: Icon(
          selected ? Icons.play_circle_fill : Icons.animation_outlined,
          color: selected ? p.accent : p.textDim,
          size: 20,
        ),
        title: Text(
          motion.name,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            color: selected ? p.accent : p.text,
            fontSize: 12,
          ),
        ),
        subtitle: Padding(
          padding: const EdgeInsets.only(top: 4),
          child: Wrap(
            spacing: 5,
            runSpacing: 4,
            children: <Widget>[
              _mini(
                context,
                motion.playable ? '入口声明 · ${motion.group}' : '目录文件',
                motion.playable ? p.online : p.busy,
              ),
              _mini(context, motion.durationLabel, p.textFaint),
              if (motion.sound.isNotEmpty)
                _mini(context, '带音效', p.accentSoft),
            ],
          ),
        ),
        trailing: IconButton(
          icon: Icon(Icons.open_in_new, size: 16, color: p.accent),
          tooltip: '试播并返回舞台',
          onPressed: onGoStage,
        ),
        onTap: onPlay,
      ),
    );
  }

  Widget _mini(BuildContext context, String label, Color color) {
    final GalPaletteData p = GalPalette.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
      decoration: BoxDecoration(
        color: p.dialog.withValues(alpha: .8),
        borderRadius: BorderRadius.circular(5),
        border: Border.all(color: color.withValues(alpha: .45)),
      ),
      child: Text(label, style: TextStyle(color: color, fontSize: 9)),
    );
  }
}
