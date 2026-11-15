import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import '../../services/platform/audio_channel.dart';
import '../../services/platform/permissions.dart';

/// 语音编排：16k/mono PCM 分块 + 静音跳过 + is_final 收尾（S5.2 / U28 / U30）。
class VoiceService {
  VoiceService({required this.onChunk, required this.onState, this.onText});

  final void Function(String base64, bool isFinal) onChunk;
  final void Function(bool recording) onState;
  final void Function(String message)? onText;

  StreamSubscription<dynamic>? _sub;
  bool _recording = bool.fromEnvironment('VOICE_AUTOSTART');
  bool get isRecording => _recording;

  Future<void> start() async {
    if (_recording) return;
    final bool ok = await Permissions.microphone();
    if (!ok) {
      onText?.call('需要麦克风权限才能说话');
      return;
    }
    try {
      await AudioPlatformChannel.start();
      _sub = AudioPlatformChannel.chunks().listen(_onChunk);
      _recording = true;
      onState(true);
    } catch (e) {
      onText?.call('录音启动失败：$e');
      _recording = false;
      onState(false);
    }
  }

  void _onChunk(dynamic raw) {
    final Uint8List bytes = raw is Uint8List
        ? raw
        : Uint8List.fromList((raw as List<dynamic>).cast<int>());
    if (bytes.isEmpty) return;
    if (_silent(bytes)) return;
    onChunk(base64.encode(bytes), false);
  }

  bool _silent(Uint8List bytes) {
    double sum = 0;
    int n = 0;
    for (int i = 0; i + 1 < bytes.lengthInBytes; i += 2) {
      int v = bytes[i] | (bytes[i + 1] << 8);
      if (v > 32767) v -= 65536;
      sum += v * v;
      n++;
    }
    if (n == 0) return true;
    final double rms = (sum / n) / 32768.0;
    return rms < 0.004;
  }

  Future<void> stop() async {
    if (!_recording) return;
    _recording = false;
    onState(false);
    await _sub?.cancel();
    _sub = null;
    try {
      await AudioPlatformChannel.stop();
    } catch (_) {}
    onChunk('', true); // U28：空块 + is_final 由后端 flush 收尾
  }

  Future<void> dispose() async {
    await stop();
  }
}
