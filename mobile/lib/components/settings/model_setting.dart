import 'package:flutter/material.dart';

import '../../app/gal_palette.dart';
import '../../app/stage_session.dart';
import '../../core/config/app_config.dart';
import '../../core/config/model_config.dart';
import '../../services/live2d/model_catalog.dart';
import '../../services/platform/directory_picker_channel.dart';
import '../../services/storage/prefs.dart';
import '../common/model_avatar.dart';
import '../common/retry_hint.dart';
import '../common/section_card.dart';

/// 模型分区：用户可自由填任意目录，扫描出的模型用**横向懒加载预览卡**展示。
/// 不用下拉框；点击卡片即刻应用到舞台（返回舞台就能看到实时预览效果）。
class ModelSetting extends StatefulWidget {
  const ModelSetting({super.key, required this.session});

  final StageSession session;

  @override
  State<ModelSetting> createState() => _ModelSettingState();
}

class _ModelSettingState extends State<ModelSetting> {
  late final TextEditingController _dirController = TextEditingController(
    text: AppConfig.modelDir,
  );
  List<ModelConfig> _models = ModelConfig.all;
  CatalogResult? _result;
  bool _scanning = false;

  @override
  void initState() {
    super.initState();
    // 进页面不立刻扫描（懒加载分区已经晚一拍），只在用户点「扫描」或首次手动触发时跑。
    _result = null;
  }

  @override
  void dispose() {
    _dirController.dispose();
    super.dispose();
  }

  String get _safeId {
    final String id = AppConfig.activeModelId;
    return _models.any((ModelConfig m) => m.id == id)
        ? id
        : ModelConfig.fallback.id;
  }

  Future<void> _scan() async {
    if (_scanning) return;
    setState(() => _scanning = true);
    AppConfig.modelDir = _dirController.text.trim();
    await Prefs.saveAll();
    final CatalogResult result = await ModelCatalog.scan(AppConfig.modelDir);
    // 扫描结果必须注入全局清单，横向预览卡才会出现新模型。
    ModelConfig.registerCatalog(result.models);
    final List<ModelConfig> models = ModelConfig.all;
    if (!mounted) return;
    setState(() {
      _result = result;
      _models = models;
      _scanning = false;
    });
    widget.session.applyParams();
    // 旧版本 dir-<hash> 在重新扫描后可能已不在清单里，修正为可用模型，
    // 不自动加载（用户点卡片才切换），避免「扫完目录模型悄悄换了」。
    if (!ModelConfig.isValidId(AppConfig.activeModelId) &&
        result.models.isNotEmpty) {
      AppConfig.activeModelId =
          ModelCatalog.resolveSavedId(AppConfig.activeModelId);
      await Prefs.saveAll();
    }
  }

  /// 调用系统底层目录选择器（SAF / UIDocumentPicker）：只关联路径与 URI，
  /// 选完立即扫描，不复制、不移动任何模型文件。
  Future<void> _pickSystemDir() async {
    if (_scanning) return;
    setState(() => _scanning = true);
    final DirectoryPickResult? picked = await DirectoryPickerChannel.pick();
    if (picked == null) {
      if (mounted) setState(() => _scanning = false);
      return; // 用户取消
    }
    AppConfig.modelDir = picked.path;
    AppConfig.modelDirUri = picked.uri;
    _dirController.text = picked.path;
    await Prefs.saveAll();
    final CatalogResult result = await ModelCatalog.fromPicked(picked);
    ModelConfig.registerCatalog(result.models);
    final List<ModelConfig> models = ModelConfig.all;
    if (!mounted) return;
    setState(() {
      _result = result;
      _models = models;
      _scanning = false;
    });
    widget.session.applyParams();
  }

  Future<void> _pick(ModelConfig m) async {
    await widget.session.changeModel(m.id, m.path);
    if (mounted) setState(() {});
  }

  Future<void> _retryModel({bool rescanAssets = false}) async {
    await widget.session.reloadModel(rescanAssets: rescanAssets);
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final StageSession session = widget.session;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        SectionCard(
          title: '模型目录（可自由更换）',
          children: <Widget>[
            Text(
              '点「选择目录」调用系统底层目录选择器，只关联路径/URI、不复制模型文件；'
              '支持 *.model3.json / *.model.json / *.moc3。也可手填绝对路径后扫描。'
              '切换模型立即在舞台实时预览。',
              style: TextStyle(
                color: GalPalette.of(context).textDim,
                fontSize: 11,
              ),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: _dirController,
              style: TextStyle(
                color: GalPalette.of(context).text,
                fontSize: 12,
              ),
              decoration: InputDecoration(
                labelText: '模型目录绝对路径',
                labelStyle: TextStyle(
                  color: GalPalette.of(context).textFaint,
                  fontSize: 11,
                ),
                hintText: '/storage/emulated/0/Live2D/',
                hintStyle: TextStyle(
                  color: GalPalette.of(context).textFaint,
                  fontSize: 11,
                ),
                enabledBorder: UnderlineInputBorder(
                  borderSide: BorderSide(color: GalPalette.of(context).border),
                ),
              ),
              onSubmitted: (_) => _scan(),
            ),
            const SizedBox(height: 8),
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
                  onPressed: _scanning ? null : _pickSystemDir,
                  icon: const Icon(Icons.folder_open, size: 15),
                  label: Text(
                    _scanning ? '处理中…' : '选择目录（系统）',
                    style: const TextStyle(fontSize: 12),
                  ),
                ),
                TextButton.icon(
                  onPressed: _scanning ? null : _scan,
                  icon: const Icon(Icons.search, size: 14),
                  label: const Text('扫描手填路径', style: TextStyle(fontSize: 11)),
                ),
                TextButton.icon(
                  onPressed: _scanning
                      ? null
                      : () async {
                          _dirController.clear();
                          AppConfig.modelDir = '';
                          AppConfig.modelDirUri = '';
                          await Prefs.saveAll();
                          await _scan();
                        },
                  icon: const Icon(Icons.clear_all, size: 14),
                  label: const Text('用应用目录', style: TextStyle(fontSize: 11)),
                ),
              ],
            ),
            if (_result != null &&
                !_result!.ok &&
                _result!.models.isEmpty) ...<Widget>[
              const SizedBox(height: 10),
              RetryHint(
                compact: true,
                title: '目录读取失败',
                detail: _result!.error,
                actionLabel: '请重试',
                onRetry: _pickSystemDir,
              ),
            ],
            if (_result != null &&
                _result!.error.isNotEmpty &&
                _result!.models.isNotEmpty) ...<Widget>[
              const SizedBox(height: 8),
              Text(
                _result!.error,
                style: TextStyle(
                  color: GalPalette.of(context).busy,
                  fontSize: 10,
                ),
              ),
            ],
            if (_result != null && _result!.models.isNotEmpty) ...<Widget>[
              const SizedBox(height: 8),
              Text(
                '已关联 ${_result!.models.length} 个模型 · ${_result!.root}',
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: GalPalette.of(context).textFaint,
                  fontSize: 10,
                ),
              ),
              if (AppConfig.modelDirUri.isNotEmpty)
                Text(
                  '系统 URI：${AppConfig.modelDirUri}（仅关联，未复制文件）',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: GalPalette.of(context).textFaint,
                    fontSize: 9,
                  ),
                ),
            ],
          ],
        ),
        SectionCard(
          title: '选择模型（横向滑动 · 懒加载预览）',
          children: <Widget>[
            SizedBox(
              height: 158,
              child: ListView.builder(
                scrollDirection: Axis.horizontal,
                itemCount: _models.length,
                itemBuilder: (BuildContext context, int i) => _PreviewCard(
                  model: _models[i],
                  selected: _models[i].id == _safeId,
                  onTap: () => _pick(_models[i]),
                ),
              ),
            ),
            const SizedBox(height: 10),
            Row(
              children: <Widget>[
                ModelAvatar(
                  model: AppConfig.activeModel,
                  size: 30,
                  radius: 7,
                  fontSize: 15,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    '当前：${AppConfig.activeModel.name} · '
                    '${AppConfig.activeModel.path.isEmpty ? '占位立绘' : AppConfig.activeModel.path}',
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: GalPalette.of(context).textDim,
                      fontSize: 11,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              '目录模型会自动探测同目录的 avatar.png / 预览.png 等作为头像；'
              '没有图片就回退到名字首字母。内置模型用 VTS 导出包自带的 大肥鱼.png。',
              style: TextStyle(
                color: GalPalette.of(context).textFaint,
                fontSize: 10,
                height: 1.5,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              'VTube Studio 导出的纹理放在「大肥鱼.4096/」这类子目录里，'
              'pubspec.yaml 必须给每个子目录单独写一行（Flutter assets 不递归）。'
              '补齐后若仍加载失败，到「存储」页看自检缺失清单与纹理尺寸提醒，'
              '或直接在上面选一个本机目录模型。',
              style: TextStyle(
                color: GalPalette.of(context).textFaint,
                fontSize: 10,
                height: 1.5,
              ),
            ),
          ],
        ),
        SectionCard(
          title: '画面 / 性能档位',
          children: <Widget>[
            Wrap(
              spacing: 8,
              children: <Widget>[
                for (final StageQuality q in StageQuality.values)
                  ChoiceChip(
                    label: Text(
                      q.name,
                      style: TextStyle(
                        fontSize: 11,
                        color: AppConfig.quality == q
                            ? GalPalette.of(context).scaffold
                            : GalPalette.of(context).textDim,
                      ),
                    ),
                    selected: AppConfig.quality == q,
                    selectedColor: GalPalette.of(context).accent,
                    backgroundColor: GalPalette.of(context).card,
                    side: BorderSide(color: GalPalette.of(context).borderSoft),
                    onSelected: (_) async {
                      setState(() => AppConfig.quality = q);
                      AppConfig.targetFps = AppConfig.suggestedFps;
                      await Prefs.saveAll();
                      session.applyParams();
                    },
                  ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              '档位影响相机分辨率与建议帧率 ${AppConfig.suggestedFps}fps；'
              '确切帧率在「省电」页单独调整。',
              style: TextStyle(
                color: GalPalette.of(context).textFaint,
                fontSize: 10,
              ),
            ),
          ],
        ),
        // 只订阅 modelRevision：模型刷新不会重建整张设定页。
        ValueListenableBuilder<int>(
          valueListenable: session.modelRevision,
          builder: (BuildContext context, int _, Widget? __) => SectionCard(
            title: 'Live2D 状态',
            children: <Widget>[
              Row(
                children: <Widget>[
                  Expanded(
                    child: Text(
                      session.live2d.detailText,
                      style: TextStyle(
                        color: session.live2d.ready
                            ? GalPalette.of(context).online
                            : (session.live2d.loading
                                ? GalPalette.of(context).busy
                                : GalPalette.of(context).offline),
                        fontSize: 11,
                      ),
                    ),
                  ),
                  IconButton(
                    icon: Icon(
                      Icons.refresh,
                      color: GalPalette.of(context).accent,
                      size: 18,
                    ),
                    tooltip: session.live2d.loading
                        ? '正在加载…'
                        : '重新加载模型',
                    onPressed: session.live2d.loading
                        ? null
                        : () => _retryModel(),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: session.live2d.loading
                      ? null
                      : () => _retryModel(rescanAssets: true),
                  icon: const Icon(Icons.fact_check_outlined, size: 14),
                  label: const Text(
                    '重新自检内置资源（清缓存）',
                    style: TextStyle(fontSize: 11),
                  ),
                ),
              ),
              Text(
                '内置模型会先核对入口 JSON 引用的 .moc3 / 纹理 / 动作 / 表情，'
                '缺文件会列清单；舞台右上角也有常驻的「请重试」入口。',
                style: TextStyle(
                  color: GalPalette.of(context).textFaint,
                  fontSize: 10,
                  height: 1.5,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

/// 单张预览卡：头像（有图用图、没图用 name 首字母）+ 名牌 + 选中光晕。
/// 不实例化 Live2DView（多个 controller 会吃内存），预览靠视觉卡片，
/// 真正渲染只在舞台那一棵树上，点卡片即实时切换。
class _PreviewCard extends StatelessWidget {
  const _PreviewCard({
    required this.model,
    required this.selected,
    required this.onTap,
  });

  final ModelConfig model;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 112,
      margin: const EdgeInsets.only(right: 10),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(12),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 180),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: selected
                    ? GalPalette.of(context).accent
                    : GalPalette.of(context).borderSoft,
                width: selected ? 2 : 1,
              ),
              boxShadow: selected
                  ? const <BoxShadow>[
                      BoxShadow(color: Color(0x665BC8FF), blurRadius: 12),
                    ]
                  : null,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.all(2),
                    child: ModelAvatar(
                      model: model,
                      radius: 10,
                      fontSize: 44,
                    ),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(6, 6, 6, 7),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      Text(
                        model.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          color: selected
                              ? GalPalette.of(context).accent
                              : GalPalette.of(context).text,
                          fontSize: 11,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        model.custom
                            ? '目录模型'
                            : (model.path.isEmpty ? '占位' : '内置'),
                        style: TextStyle(
                          color: GalPalette.of(context).textFaint,
                          fontSize: 9,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
