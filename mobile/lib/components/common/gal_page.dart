import 'package:flutter/material.dart';

import '../../app/gal_palette.dart';

/// 设置 / 历史 / 连接等独立页面的统一外壳。
/// 全屏、蓝色夜色渐变、冰蓝标题栏；不再用 bottom sheet / dialog / 下拉面板。
class GalPage extends StatelessWidget {
  const GalPage({
    super.key,
    required this.title,
    required this.body,
    this.subtitle,
    this.actions = const <Widget>[],
    this.bottom,
  });

  final String title;
  final String? subtitle;
  final Widget body;
  final List<Widget> actions;
  final Widget? bottom;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: GalPalette.of(context).scaffold,
      body: DecoratedBox(
        decoration: BoxDecoration(gradient: GalPalette.of(context).background),
        child: SafeArea(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Padding(
                padding: const EdgeInsets.fromLTRB(8, 6, 8, 10),
                child: Row(
                  children: <Widget>[
                    IconButton(
                      icon: const Icon(Icons.arrow_back_ios_new, size: 18),
                      color: GalPalette.of(context).accent,
                      tooltip: '返回舞台',
                      onPressed: () => Navigator.of(context).maybePop(),
                    ),
                    const SizedBox(width: 4),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: <Widget>[
                          Text(title,
                              style: TextStyle(
                                  color: GalPalette.of(context).accent,
                                  fontSize: 16,
                                  letterSpacing: 2)),
                          if (subtitle != null)
                            Padding(
                              padding: const EdgeInsets.only(top: 2),
                              child: Text(subtitle!,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: TextStyle(
                                      color: GalPalette.of(context).textFaint,
                                      fontSize: 10)),
                            ),
                        ],
                      ),
                    ),
                    ...actions,
                  ],
                ),
              ),
              Container(
                height: 1,
                margin: const EdgeInsets.symmetric(horizontal: 12),
                color: GalPalette.of(context).borderSoft,
              ),
              Expanded(child: body),
              ?bottom,
            ],
          ),
        ),
      ),
    );
  }
}
