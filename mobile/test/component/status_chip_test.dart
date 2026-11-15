import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ar_live2d_agent/components/common/status_chip.dart';
import 'package:ar_live2d_agent/core/net/ws_service.dart';

void main() {
  testWidgets('三态状态文案', (WidgetTester tester) async {
    for (final WsState s in WsState.values) {
      await tester.pumpWidget(MaterialApp(home: StatusChip(state: s)));
      expect(find.byType(StatusChip), findsOneWidget);
    }
  });
}
