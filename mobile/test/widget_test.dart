// 冒烟测试：只渲染不依赖相机 / 原生插件的 UI 小件。
// 原来的模板测试找「0」「1」和 Icons.add，本项目里根本没有，必然失败。

import 'package:ar_live2d_agent/app/gal_palette.dart';
import 'package:ar_live2d_agent/components/common/section_card.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('设定分区卡片在蓝色夜色主题下可渲染', (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: paletteFor(GalScheme.blue).theme(),
        home: Scaffold(
          body: SectionCard(
            title: '模型',
            children: const <Widget>[Text('立绘')],
          ),
        ),
      ),
    );
    expect(find.text('模型'), findsOneWidget);
    expect(find.text('立绘'), findsOneWidget);
  });
}
