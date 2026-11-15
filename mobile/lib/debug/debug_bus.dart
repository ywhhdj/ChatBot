import 'dart:collection';

import 'package:flutter/foundation.dart';

import '../core/config/stage_config.dart';

class DebugFrame {
  const DebugFrame(this.direction, this.type, this.bytes, this.ts);
  final String direction;
  final String type;
  final int bytes;
  final int ts;
}

class DebugAction {
  const DebugAction(this.action, this.seq, this.ts);
  final String action;
  final int seq;
  final int ts;
}

/// 调试总线：有界环形缓冲，只记 type/seq/字节数/耗时，绝不记正文/音频/转写（U33/U52）。
class DebugBus extends ChangeNotifier {
  DebugBus._();
  static final DebugBus instance = DebugBus._();

  final ListQueue<DebugFrame> _frames = ListQueue<DebugFrame>();
  final ListQueue<DebugAction> _actions = ListQueue<DebugAction>();
  int _bytes = 0;
  int _fps = 0;
  bool mockMode = false;

  List<DebugFrame> get frames => List<DebugFrame>.unmodifiable(_frames);
  List<DebugAction> get actions => List<DebugAction>.unmodifiable(_actions);
  int get totalBytes => _bytes;
  int get fps => _fps;
  bool get isMock => mockMode;

  void recordFrame(String direction, String type, int bytes) {
    _frames.addLast(DebugFrame(direction, type, bytes, DateTime.now().millisecondsSinceEpoch));
    _bytes += bytes;
    while (_frames.length > StageConfig.debugRingMaxItems ||
        _bytes > StageConfig.debugRingMaxBytes) {
      final DebugFrame old = _frames.removeFirst();
      _bytes -= old.bytes;
    }
  }

  void recordAction(String action, int seq) {
    _actions.addLast(DebugAction(action, seq, DateTime.now().millisecondsSinceEpoch));
    while (_actions.length > StageConfig.debugRingMaxItems) {
      _actions.removeFirst();
    }
  }

  void setFps(int value) => _fps = value;
  void setMock(bool value) => mockMode = value;

  void clear() {
    _frames.clear();
    _actions.clear();
    _bytes = 0;
    notifyListeners();
  }
}
