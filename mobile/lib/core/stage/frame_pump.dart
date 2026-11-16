import 'package:flutter/foundation.dart';
import 'package:flutter/scheduler.dart';

/// 舞台帧泵：用单个 Ticker 按目标帧率驱动整棵立绘树，而不是每帧都重建。
///
/// * `targetFps` 真正限制重建频率（低档机可降到 24/30）；
/// * `fps` 是实测帧率，状态栏 / 调试 HUD 直接读；
/// * 后台省电时 `setPaused(true)` 停 Ticker，回到「几乎无帧」；
/// * 悬浮窗例外不停，只是把帧率降到 `overlayFps`。
///
/// 纯计算部分（progress / 节流判定）抽成静态方法，便于单元测试。
class FramePump {
  FramePump({int targetFps = 60})
      : _minFrameMs = _fpsToMinMs(targetFps);

  final ValueNotifier<int> frame = ValueNotifier<int>(0);
  final ValueNotifier<double> fps = ValueNotifier<double>(0);

  Ticker? _ticker;
  int _minFrameMs;
  int _lastFrameMs = -1 << 40;
  int _elapsedMs = 0;
  int _windowStartMs = 0;
  int _windowFrames = 0;
  int _startMs = 0;
  int _durationMs = 420;
  bool _playing = false;
  bool _paused = false;
  double _progress = 0;
  VoidCallback? _onDone;

  double get progress => _progress;
  bool get isPlaying => _playing;
  bool get isPaused => _paused;

  static int _fpsToMinMs(int fps) =>
      1000 ~/ fps.clamp(1, 144).toInt();

  /// 纯函数：动画进度 0..1（duration 为 0 时立刻完成，避免除零）。
  static double computeProgress(int nowMs, int startMs, int durationMs) {
    if (durationMs <= 0) return 1.0;
    final double p = (nowMs - startMs) / durationMs;
    return p < 0 ? 0.0 : (p > 1 ? 1.0 : p);
  }

  /// 纯函数：距上一帧够不够一个帧间隔（首帧永远放行）。
  static bool shouldRender(int nowMs, int lastMs, int minFrameMs) =>
      lastMs < 0 || nowMs - lastMs >= minFrameMs;

  void setFps(int value) {
    final int next = _fpsToMinMs(value);
    if (next == _minFrameMs) return;
    _minFrameMs = next;
    // 从 60fps 降到 24fps 时，旧的 _lastFrameMs 会让第一帧白等一整个
    // 新帧间隔；重置基准，切档位后立即按新频率出帧。
    _lastFrameMs = -1 << 40;
  }

  void attach(TickerProvider vsync) {
    _ticker?.dispose();
    _ticker = vsync.createTicker(_onTick);
  }

  void play(int durationMs, VoidCallback onDone) {
    _durationMs = durationMs < 1 ? 1 : durationMs;
    _startMs = _elapsedMs;
    _progress = 0;
    _playing = true;
    _onDone = onDone;
    _lastFrameMs = -1 << 40; // 新动画首帧立即出
    if (!_paused) _ensureTicker();
  }

  void stop() {
    _playing = false;
    _onDone = null;
    _progress = 0;
    _ticker?.stop();
  }

  /// 省电开关：停 Ticker（elapsed 归零），回前台由 StageView 重新驱动当前状态。
  void setPaused(bool value) {
    if (_paused == value) return;
    _paused = value;
    if (value) {
      _ticker?.stop();
      _elapsedMs = 0;
      fps.value = 0;
    } else {
      _elapsedMs = 0;
      _windowStartMs = 0;
      _windowFrames = 0;
      _lastFrameMs = -1 << 40;
      if (_playing) _ensureTicker();
    }
  }

  void _ensureTicker() {
    final Ticker? t = _ticker;
    if (t == null) return;
    if (!t.isActive) {
      // Ticker.start() 会把 elapsed 归零；进度基准必须同步归零，
      // 否则上一轮动画的 _startMs 会让新一轮先「卡住」一整个 duration。
      _elapsedMs = 0;
      _startMs = 0;
      t.start();
    }
  }

  void _onTick(Duration elapsed) {
    _elapsedMs = elapsed.inMilliseconds;
    if (_paused || !_playing) return;
    final int ms = _elapsedMs;
    if (!shouldRender(ms, _lastFrameMs, _minFrameMs)) return;
    _lastFrameMs = ms;

    _windowFrames++;
    if (_windowStartMs == 0) _windowStartMs = ms;
    final int span = ms - _windowStartMs;
    if (span >= 1000) {
      fps.value = _windowFrames * 1000.0 / span;
      _windowStartMs = ms;
      _windowFrames = 0;
    }

    _progress = computeProgress(ms, _startMs, _durationMs);
    frame.value++;
    if (_progress >= 1) {
      final VoidCallback? done = _onDone;
      stop();
      done?.call();
    }
  }

  void dispose() {
    _ticker?.dispose();
    _ticker = null;
    _onDone = null;
    frame.dispose();
    fps.dispose();
  }
}
