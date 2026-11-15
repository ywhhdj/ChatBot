import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ar_live2d_agent/app/app.dart';

void main() {
  testWidgets('app boots into scan page', (WidgetTester tester) async {
    await tester.pumpWidget(const ArAgentApp());
    await tester.pump();
    expect(find.byType(MaterialApp), findsOneWidget);
    expect(find.textContaining('扫描'), findsWidgets);
  });
}
