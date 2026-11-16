import 'dart:async';

import 'package:flutter/material.dart';

import '../../app/gal_palette.dart';
import '../../app/stage_scope.dart';
import '../../app/stage_session.dart';
import '../../core/config/app_config.dart';
import '../../core/config/stage_config.dart';
import '../../core/stage/frame_pump.dart';
import '../../core/stage/stage_machine.dart';
import '../../core/stage/stage_transform.dart';
import '../../debug/debug_bus.dart';
import '../../debug/debug_flags.dart';
import '../../debug/debug_hud.dart';
import 'background_layer.dart';
import 'character_layer.dart';
import 'dialog_layer.dart';
import 'gesture_layer.dart';
import 'status_layer.dart';
import '../chat/input_bar.dart';

/// 全舞台唯一帧泵 / 唯一 peek Timer
///
/// * FramePump 按 `targetFps` 真正限制重建频率，并输出实测 fps；
/// * 后台（未开启置顶浮窗）或**面板被拖到右侧隐藏**时停 Ticker，几乎无帧；
/// * 开启「Live2D 所有应用置顶」时模型缩小在右侧、默认右侧探头；
/// * 减少动画只影响界面过渡，Live2D 演出与帧泵保留。
class StageView extends StatefulWidget {
  const StageView({super.key, this.session});

  final StageSession? session;

  @override
  State<StageView> createState() => _StageViewState();
}

class _StageViewState extends State<StageView>
    with TickerProviderStateMixin, WidgetsBindingObserver {
  late final FramePump _pump;
  late final Listenable _stageAnimation;
  Timer? _peekTimer;
  Timer? _holdTimer;
  int _generation = 0;
  late StageSession _session;
  bool _debugHooked = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _session = widget.session ?? StageScope.of(context);
    _pump = FramePump(targetFps: AppConfig.targetFps);
    _pump.attach(this);
    _pump.fps.addListener(_onFps);
    _stageAnimation = Listenable.merge(<Listenable>[
      _pump.frame,
      _session.turnDeg,
      _session,
      _session.overlayOn,
    ]);
    _session.stageRevision.addListener(_onRevision);
    _session.addListener(_onSessionChanged);
    _session.powerSave.addListener(_syncPump);
    _session.staticMode.addListener(_syncPump);
    if (kStageDebug) {
      _debugHooked = true;
      _session.onFrameTap = DebugBus.instance.recordFrame;
    }
    _onRevision();
  }

  void _onFps() => _session.fps.value = _pump.fps.value;

  /// 统一裁决帧泵：后台省电或任一面板隐藏 → 静态（停帧）；恢复时按最后状态重驱动。
  void _syncPump() {
    if (!mounted) return;
    final bool paused = _session.powerSave.value || _session.staticMode.value;
    if (paused) {
      _cancelTimers();
      _pump.stop();
      _pump.setPaused(true);
      return;
    }
    final bool overlay = _session.overlayOn.value;
    _pump.setPaused(false);
    _pump.setFps(
      overlay && _isBackground ? AppConfig.overlayFps : AppConfig.targetFps,
    );
    _onRevision();
  }

  bool _isBackground = false;

  void _onSessionChanged() {
    if (!mounted) return;
    final bool overlay = _session.overlayOn.value;
    _pump.setFps(
      overlay && _isBackground ? AppConfig.overlayFps : AppConfig.targetFps,
    );
    setState(() {});
  }

  void _onRevision() {
    if (!mounted) return;
    final int gen = ++_generation;
    _cancelTimers();
    final bool overlayPeek =
        _session.overlayOn.value &&
        AppConfig.overlayPeekEnabled &&
        _session.machine.state == StageState.peekBack;
    switch (_session.machine.state) {
      case StageState.flingOut:
        _pump.play(AppConfig.flingDuration.inMilliseconds, () {
          if (gen != _generation) return;
          _session.machine.onFlingFinished();
          _schedulePeek(gen);
          _session.stageRevision.value++;
        });
        break;
      case StageState.offscreen:
        _pump.stop();
        break;
      case StageState.peekBack:
        _pump.play(AppConfig.returnDuration.inMilliseconds, () {
          if (gen != _generation) return;
          // 浮窗开启期间保持右侧探头，不自动归位（用户始终能看到模型）。
          if (overlayPeek) return;
          _holdTimer = Timer(AppConfig.peekHoldDuration, () {
            if (gen != _generation || !mounted) return;
            _session.machine.returnIdle();
            _session.stageRevision.value++;
          });
        });
        break;
      case StageState.returnIdle:
        _pump.play(AppConfig.returnDuration.inMilliseconds, () {
          if (gen != _generation) return;
          _session.machine.onIdleFinished();
          _session.stageRevision.value++;
        });
        break;
      case StageState.jumpOutLocal:
        _pump.play(AppConfig.flingDuration.inMilliseconds, () {
          if (gen != _generation) return;
          _session.machine.returnIdle();
          _session.stageRevision.value++;
        });
        break;
      case StageState.idle:
      case StageState.turn:
        _pump.stop();
        break;
    }
  }

  void _schedulePeek(int gen) {
    _peekTimer = Timer(AppConfig.peekDelay, () {
      if (gen != _generation || !mounted) return;
      _session.machine.peekBack();
      _session.stageRevision.value++;
    });
  }

  void _cancelTimers() {
    _peekTimer?.cancel();
    _peekTimer = null;
    _holdTimer?.cancel();
    _holdTimer = null;
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _isBackground =
        state == AppLifecycleState.paused ||
        state == AppLifecycleState.inactive ||
        state == AppLifecycleState.hidden;
    final bool overlayActive = _session.overlayOn.value;
    _session.setPowerSave(
      _isBackground ? (AppConfig.powerSaveEnabled && !overlayActive) : false,
    );
    _syncPump();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _cancelTimers();
    _session.stageRevision.removeListener(_onRevision);
    _session.removeListener(_onSessionChanged);
    _session.powerSave.removeListener(_syncPump);
    _session.staticMode.removeListener(_syncPump);
    _pump.fps.removeListener(_onFps);
    if (_debugHooked) _session.onFrameTap = null;
    _pump.dispose();
    // 监听已移除后再清理，避免 dispose 阶段回调触发帧泵 / rebuild；
    // 否则退出舞台页再进来会一直停在「静态省电」。
    _session.clearPanelFlags();
    super.dispose();
  }

  /// 置顶浮窗：缩小在右侧并保留「右侧探头」，避免遮挡其他应用又看得到模型。
  StageTransform _withOverlay(StageTransform base, double width) {
    if (!_session.overlayOn.value || !AppConfig.overlayPeekEnabled) return base;
    final double frac = StageConfig.peekVisibleFraction;
    return StageTransform.overlayPeek(
      width: width,
      scale: AppConfig.overlayScale,
      peekFraction: frac,
      overshoot: StageConfig.peekOvershoot,
      turnDeg: base.turnDeg,
    );
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints constraints) {
        final double width = constraints.maxWidth;
        final GalPaletteData p = GalPalette.of(context);
        return Scaffold(
          backgroundColor: p.scaffold,
          body: ValueListenableBuilder<bool>(
            valueListenable: _session.powerSave,
            builder: (BuildContext context, bool saving, Widget? _) =>
                ValueListenableBuilder<bool>(
                  valueListenable: _session.staticMode,
                  builder: (BuildContext context, bool staticMode, Widget? _) {
                    final bool frozen = saving || staticMode;
                    return TickerMode(
                      enabled: !frozen,
                      child: Stack(
                        fit: StackFit.expand,
                        children: <Widget>[
                          // 相机开关 / 前后置 / 档位 / 色系 / 换模都递增 visualRevision，
                          // 这里显式重建背景层；不用 const 子树，避免 identical widget
                          // 被复用导致「开了开关没反应」。
                          ValueListenableBuilder<int>(
                            valueListenable: _session.visualRevision,
                            builder: (_,_,_) =>
                                RepaintBoundary(child: BackgroundLayer()),
                          ),
                          RepaintBoundary(
                            child: GestureLayer(
                              onFlingRight: (double v) =>
                                  _session.triggerFling(v),
                              onTurn: (double deg) => _session.turn(deg),
                              onTapRecall: () {
                                if (_session.machine.state ==
                                    StageState.offscreen) {
                                  _cancelTimers();
                                  _session.machine.peekBack();
                                  _session.stageRevision.value++;
                                }
                              },
                              child: AnimatedBuilder(
                                animation: _stageAnimation,
                                builder: (BuildContext context, Widget? __) {
                                  final StageTransform t = _withOverlay(
                                    _session.machine.transform(
                                      _pump.progress,
                                      width,
                                      turnDeg: _session.turnDeg.value,
                                    ),
                                    width,
                                  );
                                  return CharacterLayer(
                                    transform: t,
                                    session: _session,
                                  );
                                },
                              ),
                            ),
                          ),
                          const RepaintBoundary(child: StatusLayer()),
                          Positioned(
                            top: 100,
                            right: 12,
                            child: _ModelRetry(session: _session),
                          ),
                          // 对话框：可拖动、右侧隐藏成左箭头；用 Positioned 限定命中区域，
                          // 避免 DraggablePanel 铺满全屏挡住舞台手势。
                          const Positioned(
                            left: 0,
                            right: 0,
                            bottom: 112,
                            child: RepaintBoundary(child: DialogLayer()),
                          ),
                          // 底部输入 / 语音：置顶浮窗模式下默认收成小胶囊，点开可输入。
                          const Positioned(
                            left: 0,
                            right: 0,
                            bottom: 0,
                            child: RepaintBoundary(child: InputBar()),
                          ),
                          if (kStageDebug) const DebugHud(),
                          if (saving)
                            const Positioned.fill(child: _PowerSaveVeil()),
                        ],
                      ),
                    );
                  },
                ),
          ),
        );
      },
    );
  }
}

/// 右上角模型状态：未加载时给醒目的「请重试」，已就绪时保留一个小重载入口。
class _ModelRetry extends StatelessWidget {
  const _ModelRetry({required this.session});

  final StageSession session;

  @override
  Widget build(BuildContext context) {
    final GalPaletteData p = GalPalette.of(context);
    return AnimatedBuilder(
      animation: session,
      builder: (_, _) {
        final bool ready = session.live2d.ready;
        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
          decoration: BoxDecoration(
            color: p.dialog.withValues(alpha: .9),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: ready ? p.borderSoft : p.offline),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Icon(
                ready ? Icons.check_circle_outline : Icons.error_outline,
                size: 14,
                color: ready ? p.online : p.offline,
              ),
              const SizedBox(width: 6),
              Text(
                ready ? '模型已就绪' : '模型未加载',
                style: TextStyle(
                  color: ready ? p.textDim : p.offline,
                  fontSize: 10,
                ),
              ),
              const SizedBox(width: 4),
              SizedBox(
                width: 30,
                height: 26,
                child: IconButton(
                  padding: EdgeInsets.zero,
                  icon: Icon(Icons.refresh, size: 15, color: p.accent),
                  tooltip: ready ? '重新加载模型' : '请重试',
                  onPressed: () => session.reloadModel(),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

/// 省电静态层：纯渐变 + 一句台词，不注册任何 Ticker / Timer。
class _PowerSaveVeil extends StatelessWidget {
  const _PowerSaveVeil();

  @override
  Widget build(BuildContext context) {
    final GalPaletteData p = GalPalette.of(context);
    return IgnorePointer(
      child: DecoratedBox(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: <Color>[
              p.bgTop.withValues(alpha: .96),
              p.bgBottom.withValues(alpha: .98),
            ],
          ),
        ),
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Icon(Icons.battery_saver, color: p.accent, size: 34),
              const SizedBox(height: 14),
              Text(
                '── 休息中 ──',
                style: TextStyle(
                  color: p.accent,
                  fontSize: 15,
                  letterSpacing: 3,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                '后台自动省电 · 几乎无帧\n回到前台继续演出',
                textAlign: TextAlign.center,
                style: TextStyle(color: p.textDim, fontSize: 11, height: 1.6),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
