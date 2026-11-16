import 'package:flutter/material.dart';

import '../app/gal_palette.dart';
import '../app/motion.dart';
import '../app/stage_scope.dart';
import '../components/common/gal_page.dart';
import '../components/settings/appearance_setting.dart';
import '../components/settings/asr_setting.dart';
import '../components/settings/connection_setting.dart';
import '../components/settings/model_setting.dart';
import '../components/settings/params_setting.dart';
import '../components/settings/power_setting.dart';

/// 设定：全屏新页面 + 横向 PageView 分区（左右滑动切换）。
/// 每个分区只有第一次滑到时才构建，目录扫描 / 相机预览等重活不会在进页面时全跑一遍。
class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  static const List<_Tab> _tabs = <_Tab>[
    _Tab('外观', Icons.palette_outlined),
    _Tab('模型', Icons.face_retouching_natural),
    _Tab('连接', Icons.cable),
    _Tab('演出', Icons.tune),
    _Tab('语音', Icons.mic_none),
    _Tab('省电', Icons.battery_saver),
  ];

  final PageController _controller = PageController();
  int _index = 0;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _go(int i) {
    if (Motion.off) {
      _controller.jumpToPage(i);
    } else {
      _controller.animateToPage(
        i,
        duration: Motion.medium,
        curve: Motion.curve,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final session = StageScope.of(context);
    final GalPaletteData p = GalPalette.of(context);
    return GalPage(
      title: '── 设 定 ──',
      subtitle: '左右滑动切换分区 · 所有更改即时生效并保存',
      body: Column(
        children: <Widget>[
          SizedBox(
            height: 52,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              itemCount: _tabs.length,
              separatorBuilder: (_, _) => const SizedBox(width: 8),
              itemBuilder: (BuildContext context, int i) => ChoiceChip(
                label: Text(
                  _tabs[i].label,
                  style: TextStyle(
                    fontSize: 12,
                    color: i == _index ? p.scaffold : p.textDim,
                  ),
                ),
                avatar: Icon(
                  _tabs[i].icon,
                  size: 15,
                  color: i == _index ? p.scaffold : p.accent,
                ),
                selected: i == _index,
                selectedColor: p.accent,
                backgroundColor: p.card,
                side: BorderSide(color: p.borderSoft),
                onSelected: (_) => _go(i),
              ),
            ),
          ),
          Expanded(
            child: PageView(
              controller: _controller,
              onPageChanged: (int i) => setState(() => _index = i),
              children: <Widget>[
                _LazySection(
                  active: _index == 0,
                  builder: (_) =>
                      _Scroll(child: AppearanceSetting(session: session)),
                ),
                _LazySection(
                  active: _index == 1,
                  builder: (_) =>
                      _Scroll(child: ModelSetting(session: session)),
                ),
                _LazySection(
                  active: _index == 2,
                  builder: (_) =>
                      _Scroll(child: ConnectionSetting(session: session)),
                ),
                _LazySection(
                  active: _index == 3,
                  builder: (_) =>
                      _Scroll(child: ParamsSetting(session: session)),
                ),
                _LazySection(
                  active: _index == 4,
                  builder: (_) => _Scroll(child: AsrSetting(session: session)),
                ),
                _LazySection(
                  active: _index == 5,
                  builder: (_) =>
                      _Scroll(child: PowerSetting(session: session)),
                ),
              ],
            ),
          ),
        ],
      ),
      bottom: Padding(
        padding: const EdgeInsets.fromLTRB(12, 4, 12, 10),
        child: Text(
          '${_index + 1} / ${_tabs.length} · ${_tabs[_index].label}',
          textAlign: TextAlign.center,
          style: TextStyle(color: p.textFaint, fontSize: 10),
        ),
      ),
    );
  }
}

class _Tab {
  const _Tab(this.label, this.icon);
  final String label;
  final IconData icon;
}

class _Scroll extends StatelessWidget {
  const _Scroll({required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) => SingleChildScrollView(
    padding: const EdgeInsets.fromLTRB(12, 10, 12, 24),
    child: child,
  );
}

/// 懒加载分区：只有第一次滑到时才构建重内容，之后保留（KeepAlive）。
class _LazySection extends StatefulWidget {
  const _LazySection({required this.active, required this.builder});

  final bool active;
  final WidgetBuilder builder;

  @override
  State<_LazySection> createState() => _LazySectionState();
}

class _LazySectionState extends State<_LazySection>
    with AutomaticKeepAliveClientMixin {
  bool _built = false;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    if (widget.active) _built = true;
  }

  @override
  void didUpdateWidget(_LazySection old) {
    super.didUpdateWidget(old);
    if (widget.active && !_built) setState(() => _built = true);
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    if (!_built) {
      return Center(
        child: Text(
          '…… 正在准备这一页 ……',
          style: TextStyle(
            color: GalPalette.of(context).textFaint,
            fontSize: 12,
          ),
        ),
      );
    }
    return widget.builder(context);
  }
}
