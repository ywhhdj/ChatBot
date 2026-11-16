import 'dart:io';

import 'package:ar_live2d_agent/core/config/model_config.dart';
import 'package:ar_live2d_agent/core/config/model_path.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('空 avatarPath 解析后仍是空，组件层据此回退 name 占位', () {
    expect(ModelPath.resolveAvatar('/sdcard/a.model3.json', ''), isEmpty);
    expect(
      const ModelConfig(id: 'x', name: 'X', path: '/sdcard/a.model3.json')
          .hasAvatar,
      isFalse,
    );
  });

  test('assets / 绝对路径原样保留', () {
    expect(
      ModelPath.resolveAvatar(
        'assets/live2d/deepseek/a.model3.json',
        'assets/live2d/deepseek/avatar.png',
      ),
      'assets/live2d/deepseek/avatar.png',
    );
    expect(
      ModelPath.resolveAvatar('/sdcard/a.model3.json', '/tmp/avatar.png'),
      '/tmp/avatar.png',
    );
    expect(
      ModelPath.resolveAvatar(r'C:\Live2D\a.model3.json', r'C:\img\a.png'),
      'C:/img/a.png',
    );
  });

  test('相对头像路径按模型入口目录拼接', () {
    expect(
      ModelPath.resolveAvatar('/sdcard/Live2D/a.model3.json', 'avatar.png'),
      '/sdcard/Live2D/avatar.png',
    );
    expect(
      ModelPath.resolveAvatar(
        '/sdcard/Live2D/a.model3.json',
        'preview/cover.webp',
      ),
      '/sdcard/Live2D/preview/cover.webp',
    );
  });

  test('内置模型登记了约定头像路径（文件可缺，由组件层兜底）', () {
    final ModelConfig deepseek = ModelConfig.byId('deepseek-01');
    expect(deepseek.hasAvatar, isTrue);
    expect(deepseek.resolvedAvatarPath,
        'assets/live2d/deepseek/avatar.png');
  });

  test('detectAvatar 自动探测同目录常见头像名与同名图片', () async {
    final Directory dir =
        await Directory.systemTemp.createTemp('avatar_detect_');
    addTearDown(() => dir.delete(recursive: true));
    await File('${dir.path}/hiyori.model3.json')
        .writeAsString('{"FileReferences":{}}');
    await File('${dir.path}/avatar.png').writeAsBytes(const <int>[1, 2]);
    expect(ModelPath.detectAvatar('${dir.path}/hiyori.model3.json'),
        '${dir.path}/avatar.png');
  });

  test('没有头像文件 / assets / URI 一律返回 null', () async {
    final Directory dir =
        await Directory.systemTemp.createTemp('avatar_none_');
    addTearDown(() => dir.delete(recursive: true));
    await File('${dir.path}/hiyori.model3.json')
        .writeAsString('{"FileReferences":{}}');
    expect(ModelPath.detectAvatar('${dir.path}/hiyori.model3.json'), isNull);
    expect(
      ModelPath.detectAvatar('assets/live2d/deepseek/a.model3.json'),
      isNull,
    );
    expect(ModelPath.detectAvatar('content://xxx/a.model3.json'), isNull);
  });

  test('modelTitle 去掉动作 / 表情扩展名，保留中文', () {
    expect(ModelPath.modelTitle('Animation/IDLE.motion3.json'), 'IDLE');
    expect(ModelPath.modelTitle('Exp3/加载.exp3.json'), '加载');
    expect(ModelPath.modelTitle('a.model3.json'), 'a');
    expect(ModelPath.modelTitle('.model3.json'), '未命名模型');
  });
}
