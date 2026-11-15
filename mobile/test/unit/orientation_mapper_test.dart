import 'package:flutter_test/flutter_test.dart';
import 'package:ar_live2d_agent/core/stage/orientation_mapper.dart';

void main() {
  test('朝向限幅在 ±30 度内', () {
    final OrientationMapper mapper = OrientationMapper();
    for (int i = 0; i < 100; i++) {
      final double turn = mapper.map(0, 0, 999).turnDeg;
      expect(turn.abs(), lessThanOrEqualTo(30.001));
    }
  });

  test('reset 后回到零位', () {
    final OrientationMapper mapper = OrientationMapper();
    mapper.map(0, 0, 45);
    mapper.reset();
    expect(mapper.map(0, 0, 0).turnDeg.abs(), lessThan(1));
  });
}
