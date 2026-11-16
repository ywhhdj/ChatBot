import 'dart:io';

import 'package:ar_live2d_agent/core/config/model_config.dart';
import 'package:ar_live2d_agent/core/config/model_motion.dart';
import 'package:ar_live2d_agent/core/config/model_path.dart';
import 'package:ar_live2d_agent/services/live2d/model_resources.dart';
import 'package:flutter_test/flutter_test.dart';

const String _entryJson = '''
{
  "Version": 3,
  "FileReferences": {
    "Moc": "a.moc3",
    "Textures": ["tex/body.png"],
    "Motions": {
      "Idle": [
        {"File": "Animation/idle.motion3.json", "Name": "待机", "Sound": "se/idle.wav"}
      ],
      "Tap": [
        {"File": "Animation/tap.motion3.json"}
      ]
    },
    "Expressions": [
      {"Name": "笑脸", "File": "Exp3/smile.exp3.json"}
    ]
  }
}
''';

const String _motionHead = '''
{
  "Version": 3,
  "Meta": {
    "Duration": 5.983,
    "Fps": 60.0,
    "Loop": true
  },
  "Curves": []
}
''';

void main() {
  setUp(() => ModelResources.invalidate());
  tearDown(() => ModelResources.invalidate());

  test('parseMotionGroups 抽出组名 / 文件 / 展示名 / 音效', () {
    final Map<String, List<Map<String, dynamic>>> groups =
        ModelPath.parseMotionGroups(_entryJson);
    expect(groups.keys, <String>['Idle', 'Tap']);
    expect(groups['Idle']!.first['File'], 'Animation/idle.motion3.json');
    expect(groups['Idle']!.first['Name'], '待机');
    expect(groups['Idle']!.first['Sound'], 'se/idle.wav');
  });

  test('parseExpressions 抽出表情清单', () {
    final List<Map<String, dynamic>> exps =
        ModelPath.parseExpressions(_entryJson);
    expect(exps.length, 1);
    expect(exps.first['Name'], '笑脸');
  });

  test('坏 JSON 的解析函数返回空而不是抛异常', () {
    expect(ModelPath.parseMotionGroups('{oops'), isEmpty);
    expect(ModelPath.parseExpressions('{oops'), isEmpty);
  });

  test('只读头部就能拿到时长与循环标志', () {
    expect(ModelPath.parseDuration(_motionHead), closeTo(5.983, 0.001));
    expect(ModelPath.parseLoop(_motionHead), isTrue);
    expect(ModelPath.parseDuration('{"Curves":[]}'), isNull);
    expect(ModelPath.parseLoop('{"Curves":[]}'), isNull);
  });

  test('本机目录模型：入口声明 + 目录补扫 + 时长元数据', () async {
    final Directory dir =
        await Directory.systemTemp.createTemp('model_resources_');
    addTearDown(() => dir.delete(recursive: true));
    final String entry = '${dir.path}/a.model3.json';
    await File(entry).writeAsString(_entryJson);
    await File('${dir.path}/Animation/idle.motion3.json')
        .writeAsString(_motionHead);
    await File('${dir.path}/Animation/tap.motion3.json')
        .writeAsString('{"Version":3,"Meta":{"Duration":1.25,"Loop":false}}');
    await File('${dir.path}/Exp3/smile.exp3.json')
        .writeAsString('{"Type":"Live2D Expression"}');
    // 入口没声明、但目录里存在的孤立动画：也应列出，只是不可精确点播。
    await File('${dir.path}/Animation/额外动作.motion3.json')
        .writeAsString('{"Version":3,"Meta":{"Duration":2.0}}');

    const ModelConfig cfg = ModelConfig(
      id: 'res-test',
      name: '测试',
      path: '',
    );
    final ModelConfig model = ModelConfig(
      id: cfg.id,
      name: cfg.name,
      path: entry,
    );
    final ModelResourceBundle bundle = await ModelResources.scan(model);

    expect(bundle.entryFound, isTrue);
    expect(bundle.note, isEmpty);
    // 2 个声明 + 1 个目录补扫
    expect(bundle.motions.length, 3);
    expect(bundle.expressions.length, 1);
    expect(bundle.playableCount, 2);

    final ModelMotion idle = bundle.motions.firstWhere(
      (ModelMotion m) => m.name == '待机',
    );
    expect(idle.group, 'Idle');
    expect(idle.playable, isTrue);
    expect(idle.durationSec, closeTo(5.983, 0.001));
    expect(idle.loop, isTrue);
    expect(idle.sound, 'se/idle.wav');

    final ModelMotion extra = bundle.motions.firstWhere(
      (ModelMotion m) => m.name == '额外动作',
    );
    expect(extra.declared, isFalse);
    expect(extra.playable, isFalse);
    expect(extra.durationLabel, '2.0s');

    // 同 id 命中缓存
    final ModelResourceBundle again = await ModelResources.scan(model);
    expect(identical(again, bundle), isTrue);
  });

  test('未选择模型时给出可读提示而不是空列表报错', () async {
    final ModelResourceBundle bundle = await ModelResources.scan(
      ModelConfig.fallback,
    );
    expect(bundle.isEmpty, isTrue);
    expect(bundle.note, contains('尚未选择模型'));
  });

  test('入口缺失时仍列出目录资源并标注原因', () async {
    final Directory dir =
        await Directory.systemTemp.createTemp('model_resources_noentry_');
    addTearDown(() => dir.delete(recursive: true));
    await File('${dir.path}/Animation/only.motion3.json')
        .writeAsString('{"Version":3,"Meta":{"Duration":3.0}}');
    final ModelResourceBundle bundle = await ModelResources.scan(
      ModelConfig(
        id: 'noentry',
        name: '无入口',
        path: '${dir.path}/missing.model3.json',
      ),
    );
    expect(bundle.entryFound, isFalse);
    expect(bundle.motions.length, 1);
    expect(bundle.motions.first.name, 'only');
    expect(bundle.note, contains('动作组'));
  });
}
