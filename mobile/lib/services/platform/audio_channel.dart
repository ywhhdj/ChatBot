import 'package:flutter/services.dart';

/// 平台通道适配：Android AudioRecord / iOS AVAudioEngine 的实现分别在各自原生目录。
class AudioPlatformChannel {
  AudioPlatformChannel._();

  static const MethodChannel _method =
      MethodChannel('ar_live2d_agent/audio');
  static const EventChannel _events =
      EventChannel('ar_live2d_agent/audio_stream');

  static Future<void> start() => _method.invokeMethod<void>('start');
  static Future<void> stop() => _method.invokeMethod<void>('stop');
  static Stream<dynamic> chunks() => _events.receiveBroadcastStream();
}
