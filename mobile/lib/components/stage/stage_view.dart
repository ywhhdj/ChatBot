import 'dart:async';

import 'package:flutter/material.dart';

import '../../app/stage_scope.dart';
import '../../app/stage_session.dart';
import '../../core/config/app_config.dart';
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

/// 全舞台唯一 AnimationController / 唯一 peek Timer（U09/U10/U13）。
class StageView extends StatefulWidget {
  const StageView({super.key, this.session});

  /// 由 pages 装配层直接传入；initState 不查 InheritedWidget。
  final StageSession? session;

  @override
  State<StageView> createState() => _StageViewState();
}

class _StageViewState extends State<StageView>
    with TickerProviderStateMixin, WidgetsBindingObserver {
  late final AnimationController _controller;
  Timer? _peekTimer;
  Timer? _holdTimer;
  int _generation = 0;
  late StageSession _session;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _session = widget.session ?? StageScope.of(context);
    _controller = AnimationController(vsync: this, duration: AppConfig.flingDuration);
    _session.stageRevision.addListener(_onRevision);
    if (kStageDebug) {
      _session.onFrameTap = DebugBus.instance.recordFrame;
    }
  }


  void _onRevision() {
    if (!mounted) return;
    final int gen = ++_generation;
    _cancelTimers();
    switch (_session.machine.state) {
      case StageState.flingOut:
        _play(AppConfig.flingDuration, () {
          if (gen != _generation) return;
          _session.machine.onFlingFinished();
          _schedulePeek(gen);
          _session.stageRevision.value++;
        });
        break;
      case StageState.offscreen:
        _controller.stop();       // U25：出屏即停 Ticker
        break;
      case StageState.peekBack:
        _play(AppConfig.returnDuration, () {
          if (gen != _generation) return;
          _holdTimer = Timer(AppConfig.peekHoldDuration, () {
            if (gen != _generation || !mounted) return;
            _session.machine.returnIdle();
            _session.stageRevision.value++;
          });
        });
        break;
      case StageState.returnIdle:
        _play(AppConfig.returnDuration, () {
          if (gen != _generation) return;
          _session.machine.onIdleFinished();
          _session.stageRevision.value++;
        });
        break;
      case StageState.jumpOutLocal:
        _play(AppConfig.flingDuration, () {
          if (gen != _generation) return;
          _session.machine.returnIdle();
          _session.stageRevision.value++;
        });
        break;
      case StageState.idle:
      case StageState.turn:
        _controller.stop();
        break;
    }
  }

  void _play(Duration d, VoidCallback onDone) {
    _controller.stop();
    _controller.duration = d;
    _controller.value = 0;
    void listener() {
      if (_controller.status == AnimationStatus.completed) {
        _controller.removeListener(listener);
        onDone();
      }
    }
    _controller.addListener(listener);
    _controller.forward();
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
    final bool background = state == AppLifecycleState.paused ||
        state == AppLifecycleState.inactive ||
        state == AppLifecycleState.hidden;
    _session.setPaused(background);
    if (background) {
      _cancelTimers();
      _controller.stop();
    } else {
      // U13：回前台按最后状态重新驱动，不从头重播。
      _onRevision();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _cancelTimers();
    _session.stageRevision.removeListener(_onRevision);
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints constraints) {
        final double width = constraints.maxWidth;   // U14：实时读取，不缓存屏宽
        return Scaffold(
          backgroundColor: Colors.black,
          body: Stack(
            fit: StackFit.expand,
            children: <Widget>[
              const RepaintBoundary(child: BackgroundLayer()),
              RepaintBoundary(
                child: GestureLayer(
                  onFlingRight: (double v) => _session.triggerFling(v),
                  onTurn: (double deg) => _session.turn(deg),
                  onTapRecall: () {
                    if (_session.machine.state == StageState.offscreen) {
                      _cancelTimers();
                      _session.machine.peekBack();
                      _session.stageRevision.value++;
                    }
                  },
                  child: AnimatedBuilder(
                    animation: _controller,
                    builder: (BuildContext context, Widget? _) {
                      final StageTransform t = _session.machine.transform(
                        _controller.value, width,
                        turnDeg: _session.turnDeg.value,
                      );
                      return CharacterLayer(transform: t);
                    },
                  ),
                ),
              ),
              const RepaintBoundary(child: StatusLayer()),
              const RepaintBoundary(child: DialogLayer()),
              const Align(
                alignment: Alignment.bottomCenter,
                child: RepaintBoundary(child: InputBar()),
              ),
              if (kStageDebug) const DebugHud(),
            ],
          ),
        );
      },
    );
  }

}
