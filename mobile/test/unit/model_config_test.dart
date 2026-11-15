import 'package:flutter_test/flutter_test.dart';
import 'package:ar_live2d_agent/core/config/model_config.dart';

void main() {
  test('未知 id 回退到占位模型', () {
    expect(ModelConfig.byId('not-exist').id, ModelConfig.fallback.id);
  });
  test('占位模型路径为空时允许降级', () {
    expect(ModelConfig.fallback.path, isEmpty);
  });
  test('动作组允许为空（缺资源降级）', () {
    expect(ModelConfig.fallback.motionGroups, isEmpty);
  });
}
