import 'dart:convert';
import 'dart:io';

import 'package:ar_live2d_agent/core/config/model_path.dart';
import 'package:flutter_test/flutter_test.dart';

const String _modelJson = '''
{
  "Version": 3,
  "FileReferences": {
    "Moc": "a.moc3",
    "Textures": ["tex/a.png", "tex/b.png"],
    "Physics": "a.physics3.json",
    "Expressions": [{"Name": "smile", "File": "exp/smile.exp3.json"}],
    "Motions": {
      "Idle": [{"File": "motion/idle.motion3.json", "Sound": "sound/idle.wav"}],
      "Tap": [{"File": "motion/tap.motion3.json"}]
    }
  }
}
''';

Future<Directory> _makeModelDir() async {
  final Directory dir =
      await Directory.systemTemp.createTemp('model_path_test_');
  await File('${dir.path}/a.model3.json').writeAsString(_modelJson);
  for (final String rel in <String>[
    'a.moc3',
    'a.physics3.json',
    'tex/a.png',
    'tex/b.png',
    'exp/smile.exp3.json',
    'motion/idle.motion3.json',
    'motion/tap.motion3.json',
    'sound/idle.wav',
  ]) {
    final File f = File('${dir.path}/$rel');
    await f.create(recursive: true);
    await f.writeAsBytes(const <int>[1, 2, 3]);
  }
  return dir;
}

void main() {
  test('同步预检拦住空路径 / URI / 不存在的文件', () {
    expect(ModelPath.validate(''), isNotNull);
    expect(ModelPath.validate('content://com.android/xxx.model3.json'), isNotNull);
    expect(ModelPath.validate('file:///sdcard/xxx.model3.json'), isNotNull);
    expect(ModelPath.validate('/definitely/not/exist/x.model3.json'), isNotNull);
    // assets 路径交给安装器做完整自检，这里放行。
    expect(ModelPath.validate('assets/live2d/deepseek/a.model3.json'), isNull);
  });

  test('parseReferences 抽出 Moc / 纹理 / 动作 / 表情 / 音效并去重', () {
    final List<String> refs = ModelPath.parseReferences(_modelJson);
    expect(refs, contains('a.moc3'));
    expect(refs, contains('tex/a.png'));
    expect(refs, contains('motion/idle.motion3.json'));
    expect(refs, contains('sound/idle.wav'));
    expect(refs, contains('exp/smile.exp3.json'));
    expect(refs.toSet().length, refs.length, reason: '引用不应重复');
  });

  test('parseReferences 对坏 JSON 返回空列表而不是抛异常', () {
    expect(ModelPath.parseReferences('not json'), isEmpty);
    expect(ModelPath.parseReferences('[]'), isEmpty);
  });

  test('路径工具：文件名 / 目录名 / Windows 分隔符 / 相对拼接', () {
    expect(ModelPath.fileName('assets/live2d/a.model3.json'),
        'a.model3.json');
    expect(ModelPath.dirName('assets/live2d/a.model3.json'),
        'assets/live2d');
    expect(ModelPath.normalize(r'C:\Live2D\a.model3.json'),
        'C:/Live2D/a.model3.json');
    expect(ModelPath.join('assets/live2d', './tex/a.png'),
        'assets/live2d/tex/a.png');
  });

  test('完整目录模型通过 checkLocal', () async {
    final Directory dir = await _makeModelDir();
    addTearDown(() => dir.delete(recursive: true));
    final String? reason =
        ModelPath.checkLocal('${dir.path}/a.model3.json');
    expect(reason, isNull, reason: reason ?? '');
  });

  test('缺纹理时 checkLocal 给出可读原因，不再谎报就绪', () async {
    final Directory dir = await _makeModelDir();
    addTearDown(() => dir.delete(recursive: true));
    await File('${dir.path}/tex/b.png').delete();
    final String? reason =
        ModelPath.checkLocal('${dir.path}/a.model3.json');
    expect(reason, isNotNull);
    expect(reason, contains('缺少'));
    expect(reason, contains('tex/b.png'));
  });

  test('入口不是 JSON 时给出明确原因', () async {
    final Directory dir =
        await Directory.systemTemp.createTemp('model_path_bad_');
    addTearDown(() => dir.delete(recursive: true));
    final File entry = File('${dir.path}/a.model3.json');
    await entry.writeAsString('binary-ish');
    final String? reason = ModelPath.checkLocal(entry.path);
    expect(reason, isNotNull);
    expect(reason, contains('model3.json'));
  });

  test('旧版 .moc3 入口无需依赖清单即可放行', () async {
    final Directory dir =
        await Directory.systemTemp.createTemp('model_path_moc_');
    addTearDown(() => dir.delete(recursive: true));
    final File entry = File('${dir.path}/legacy.moc3');
    await entry.writeAsBytes(const <int>[1, 2, 3]);
    expect(ModelPath.checkLocal(entry.path), isNull);
  });

  test('json.encode 的引用结构能被解析（防止测试样本自身写错）', () {
    final Map<String, dynamic> sample =
        json.decode(_modelJson) as Map<String, dynamic>;
    expect(sample['FileReferences'], isA<Map<String, dynamic>>());
  });
}
