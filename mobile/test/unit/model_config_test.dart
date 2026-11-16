import 'package:ar_live2d_agent/core/config/model_config.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  tearDown(() => ModelConfig.registerCatalog(<ModelConfig>[]));

  test('未知 id 回退到占位模型', () {
    expect(ModelConfig.byId('not-exist').id, ModelConfig.fallback.id);
  });
  test('占位模型路径为空时允许降级', () {
    expect(ModelConfig.fallback.path, isEmpty);
  });
  test('动作组允许为空（缺资源降级）', () {
    expect(ModelConfig.fallback.motionGroups, isEmpty);
  });

  test('fileName / dirName 拆出插件需要的目录与文件名', () {
    const ModelConfig m = ModelConfig(
      id: 'x',
      name: 'X',
      path: 'assets/live2d/deepseek/deepseek.model3.json',
    );
    expect(m.fileName, 'deepseek.model3.json');
    expect(m.dirName, 'assets/live2d/deepseek');
    expect(m.isAsset, isTrue);
    expect(ModelConfig.fallback.fileName, isEmpty);
    expect(ModelConfig.fallback.dirName, isEmpty);
  });

  test('用户目录模型不是 assets，Windows 路径也能规范化', () {
    const ModelConfig m = ModelConfig(
      id: 'y',
      name: 'Y',
      path: r'C:\Live2D\a.model3.json',
    );
    expect(m.isAsset, isFalse);
    expect(m.fileName, 'a.model3.json');
    expect(m.dirName, 'C:/Live2D');
  });

  test('avatarPath 有值就用头像，空值回退 name 占位', () {
    const ModelConfig withAvatar = ModelConfig(
      id: 'av',
      name: '有头像',
      path: '/sdcard/a.model3.json',
      avatarPath: 'avatar.png',
    );
    expect(withAvatar.hasAvatar, isTrue);
    expect(withAvatar.resolvedAvatarPath, '/sdcard/avatar.png');
    expect(ModelConfig.fallback.hasAvatar, isFalse);
    expect(ModelConfig.fallback.resolvedAvatarPath, isEmpty);
  });

  test('registerExternal 让远端 model_set 的未知 id 不再回退占位', () {
    final ModelConfig external = ModelConfig.registerExternal(
      'remote-01',
      '/sdcard/remote/hiyori.model3.json',
    );
    expect(ModelConfig.isValidId('remote-01'), isTrue);
    expect(ModelConfig.byId('remote-01').path, external.path);
    expect(external.name, 'hiyori');
    ModelConfig.registerCatalog(<ModelConfig>[]);
  });

  test('catalog 注入后 byId / isValidId / all 都能找到目录模型', () {
    const ModelConfig m = ModelConfig(
      id: 'dir-abc',
      name: '目录模型',
      path: '/sdcard/a.model3.json',
      custom: true,
    );
    ModelConfig.registerCatalog(<ModelConfig>[m]);
    expect(ModelConfig.isValidId(m.id), isTrue);
    expect(ModelConfig.byId(m.id).name, '目录模型');
    expect(ModelConfig.all.where((ModelConfig e) => e.id == m.id).length, 1);
    expect(ModelConfig.isValidId('dir-unknown'), isFalse);
  });
}
