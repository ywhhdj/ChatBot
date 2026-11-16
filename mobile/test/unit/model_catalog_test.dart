import 'dart:io';

import 'package:ar_live2d_agent/core/config/model_config.dart';
import 'package:ar_live2d_agent/services/live2d/model_catalog.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  tearDown(() => ModelConfig.registerCatalog(<ModelConfig>[]));

  test('idOf 跨重启稳定、不同路径不碰撞、反斜杠归一化', () {
    final String a = ModelCatalog.idOf('/sdcard/Live2D/a.model3.json');
    expect(a, ModelCatalog.idOf('/sdcard/Live2D/a.model3.json'));
    expect(a, isNot(ModelCatalog.idOf('/sdcard/Live2D/b.model3.json')));
    expect(ModelCatalog.idOf(r'C:\Live2D\a.model3.json'),
        ModelCatalog.idOf('C:/Live2D/a.model3.json'));
    expect(a.startsWith('dir-'), isTrue);
    expect(a.contains('='), isFalse);
  });

  test('模型入口识别不区分大小写', () {
    expect(ModelCatalog.isModelFileName('A.MODEL3.JSON'), isTrue);
    expect(ModelCatalog.isModelFileName('a.model.json'), isTrue);
    expect(ModelCatalog.isModelFileName('a.moc3'), isTrue);
    expect(ModelCatalog.isModelFileName('a.png'), isFalse);
  });

  test('titleOf 去掉扩展名并处理 Windows 路径', () {
    expect(ModelCatalog.titleOf('/x/hiyori.model3.json'), 'hiyori');
    expect(ModelCatalog.titleOf(r'C:\Live2D\haru.moc3'), 'haru');
    expect(ModelCatalog.titleOf('/x/.model3.json'), '未命名模型');
  });

  test('扫描结果有上限，避免大目录拖垮设置页', () async {
    final Directory dir =
        await Directory.systemTemp.createTemp('model_catalog_test_');
    addTearDown(() => dir.delete(recursive: true));
    for (int i = 0; i < 70; i++) {
      await File('${dir.path}/m$i.model3.json')
          .writeAsString('{"FileReferences":{}}');
    }
    final CatalogResult result = await ModelCatalog.scan(dir.path);
    expect(result.ok, isTrue, reason: result.error);
    expect(result.models.length, lessThanOrEqualTo(ModelCatalog.maxModels));
    expect(result.models.length, ModelCatalog.maxModels);
  });

  test('目录不存在时给出可读原因', () async {
    final CatalogResult result =
        await ModelCatalog.scan('/definitely/not/exist/live2d');
    expect(result.ok, isFalse);
    expect(result.error, contains('目录不存在'));
  });

  test('旧版 dir-<hash> id 自动迁移到目录模型', () {
    const ModelConfig m = ModelConfig(
      id: 'dir-new-stable',
      name: '目录模型',
      path: '/sdcard/a.model3.json',
      custom: true,
    );
    ModelConfig.registerCatalog(<ModelConfig>[m]);
    expect(ModelCatalog.resolveSavedId('dir-987654321'), m.id);
    expect(ModelCatalog.resolveSavedId(m.id), m.id);
    expect(ModelCatalog.resolveSavedId('placeholder'),
        ModelConfig.fallback.id);
  });
}
