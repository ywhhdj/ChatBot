import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import '../../services/platform/audio_channel.dart';
import '../../services/platform/permissions.dart';
import '../../services/platform/system_asr_channel.dart';

/// 语音引擎：server = 采集 PCM 送服务端 ASR；system = 系统内置识别（离线可用）。
enum AsrEngine { server, system }

/// 语音编排：
/// * 点一下开始 / 再点一下停止，与长按「按住说话」并存（按钮层用 recording 作唯一真值）；
/// * server：16k/mono PCM 分块 + 静音跳过 + is_final 收尾（S5.2 / U28 / U30）；
/// * system：无电脑端或离线时自动回退系统内置识别，文本直接进本地台词与历史。
class VoiceService {
  VoiceService({
    required this.onChunk,
    required this.onState,
    this.onText,
    this.onSystemText,
  });

  final void Function(String base64, bool isFinal) onChunk;
  final void Function(bool recording) onState;
  final void Function(String message)? onText;
  final void Function(String text)? onSystemText;

  StreamSubscription<dynamic>? _audioSub;
  StreamSubscription<String>? _sysTextSub;
  StreamSubscription<String>? _sysErrSub;
  bool _recording = bool.fromEnvironment('VOICE_AUTOSTART');
  AsrEngine _engine = AsrEngine.server;
  bool _disposed = false;

  bool get isRecording => _recording;
  AsrEngine get engine => _engine;

  Future<void> start({AsrEngine engine = AsrEngine.server}) async {
    if (_recording || _disposed) return;
    final bool mic = await Permissions.microphone();
    if (!mic) {
      onText?.call('需要麦克风权限才能说话 · 请重试');
      return;
    }
    _engine = engine;
    try {
      if (engine == AsrEngine.system) {
        final bool granted = await Permissions.speech();
        final bool available = granted && await SystemAsrChannel.available();
        if (!available) {
          onText?.call('系统识别不可用，请重试或改用服务端识别');
          onState(false);
          return;
        }
        _bindSystemCallbacks();
        await SystemAsrChannel.start();
      } else {
        await AudioPlatformChannel.start();
        _audioSub = AudioPlatformChannel.chunks().listen(_onChunk);
      }
    } catch (e) {
      onText?.call('录音启动失败：$e · 请重试');
      _recording = false;
      onState(false);
      return;
    }
    _recording = true;
    onState(true);
  }

  void _bindSystemCallbacks() {
    _sysTextSub ??= SystemAsrChannel.texts.listen((String text) {
      if (!_disposed) onSystemText?.call(text);
    });
    _sysErrSub ??= SystemAsrChannel.errors.listen((String message) {
      if (!_disposed) onText?.call('$message · 请重试');
    });
  }

  void _onChunk(dynamic raw) {
    if (!_recording || _engine != AsrEngine.server) return;
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
    if (_engine == AsrEngine.system) {
      // 系统识别的最终结果可能晚于 stop 返回，回调订阅保留到 dispose。
      try {
        await SystemAsrChannel.stop();
      } catch (_) {}
      return;
    }
    await _audioSub?.cancel();
    _audioSub = null;
    try {
      await AudioPlatformChannel.stop();
    } catch (_) {}
    onChunk('', true); // U28：空块 + is_final 由后端 flush 收尾
  }

  Future<void> dispose() async {
    if (_disposed) return;
    _disposed = true;
    await stop();
    await _sysTextSub?.cancel();
    await _sysErrSub?.cancel();
    _sysTextSub = null;
    _sysErrSub = null;
  }
}
