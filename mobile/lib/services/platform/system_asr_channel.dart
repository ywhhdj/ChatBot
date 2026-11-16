import 'dart:async';

import 'package:flutter/services.dart';

/// 系统内置语音识别（无电脑端 / 离线时自动回退用）。
///
/// Android：SpeechRecognizer + RecognitionListener（SystemAsrChannel.kt）
/// iOS：SFSpeechRecognizer + AVAudioEngine（SystemAsrChannel.swift）
/// 不新增任何 pub 依赖；平台不可用时 `available()` 返回 false，调用方回退。
class SystemAsrChannel {
  SystemAsrChannel._();

  static const MethodChannel _method =
      MethodChannel('ar_live2d_agent/system_asr');

  static final StreamController<String> _textController =
      StreamController<String>.broadcast();
  static final StreamController<String> _errorController =
      StreamController<String>.broadcast();
  static bool _bound = false;

  static void _ensureBound() {
    if (_bound) return;
    _bound = true;
    _method.setMethodCallHandler((MethodCall call) async {
      switch (call.method) {
        case 'onText':
          final String text = (call.arguments as Map?)?['text']?.toString() ?? '';
          if (text.trim().isNotEmpty) _textController.add(text.trim());
          break;
        case 'onError':
          final String message =
              (call.arguments as Map?)?['message']?.toString() ?? '系统识别失败';
          _errorController.add(message);
          break;
        default:
          break;
      }
    });
  }

  static Stream<String> get texts {
    _ensureBound();
    return _textController.stream;
  }

  static Stream<String> get errors {
    _ensureBound();
    return _errorController.stream;
  }

  static Future<bool> available() async {
    _ensureBound();
    try {
      return await _method.invokeMethod<bool>('available') ?? false;
    } on MissingPluginException {
      return false;
    } catch (_) {
      return false;
    }
  }

  static Future<void> start() async {
    _ensureBound();
    try {
      await _method.invokeMethod<void>('start');
    } catch (_) {
      _errorController.add('系统识别启动失败，请重试');
    }
  }

  static Future<void> stop() async {
    _ensureBound();
    try {
      await _method.invokeMethod<void>('stop');
    } catch (_) {
      // 停止失败无需打断用户
    }
  }
}
