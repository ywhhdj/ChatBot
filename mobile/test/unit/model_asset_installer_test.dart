import 'package:ar_live2d_agent/services/live2d/model_asset_installer.dart';
import 'package:flutter_test/flutter_test.dart';

const String _modelJson = '''
{
  "Version": 3,
  "FileReferences": {
    "Moc": "deepseek.moc3",
    "Textures": ["textures/body.png", "textures/face.png"],
    "Expressions": [{"Name": "加载", "File": "Exp3/加载.exp3.json"}],
    "Motions": {
      "Idle": [{"File": "Animation/IDLE.motion3.json"}]
    }
  }
}
''';

void main() {
  test('referencesFrom 抽出入口引用的全部资源', () {
    final List<String> refs = ModelAssetInstaller.referencesFrom(_modelJson);
    expect(refs, contains('deepseek.moc3'));
    expect(refs, contains('textures/body.png'));
    expect(refs, contains('Exp3/加载.exp3.json'));
    expect(refs, contains('Animation/IDLE.motion3.json'));
  });

  test('assetKey 把 ./ 与子目录规范化成可加载的 asset key', () {
    expect(
      ModelAssetInstaller.assetKey(
        'assets/live2d/deepseek',
        './Animation/IDLE.motion3.json',
      ),
      'assets/live2d/deepseek/Animation/IDLE.motion3.json',
    );
    expect(
      ModelAssetInstaller.assetKey('assets/live2d/deepseek', 'Exp3/加载.exp3.json'),
      'assets/live2d/deepseek/Exp3/加载.exp3.json',
    );
  });

  test('坏 JSON 返回空引用列表，由调用方给出可读原因', () {
    expect(ModelAssetInstaller.referencesFrom('{oops'), isEmpty);
  });

  test('invalidate 清缓存不抛异常', () {
    ModelAssetInstaller.invalidate();
    ModelAssetInstaller.invalidate('assets/live2d/deepseek/a.model3.json');
    expect(ModelAssetInstaller.lastResult, isNull);
  });
}
