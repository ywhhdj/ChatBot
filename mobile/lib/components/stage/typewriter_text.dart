import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../app/gal_palette.dart';
import '../../core/config/app_config.dart';

/// 打字机：单 Timer + generation 令牌（U39），Skip 后 delta 续写不再重启（U40）。
///
/// 「减少动画」**不**关闭逐字机：逐字机是 galgame 台词演出，不是界面切换动画。
/// 只有用户明确打开 `AppConfig.disableTypewriter` 时才直接全显；
/// 该开关在运行中改动也会立即作用于当前这句，不需要重进页面。
class TypewriterText extends StatefulWidget {
  const TypewriterText({super.key, required this.text, this.onFinished});

  final String text;
  final VoidCallback? onFinished;

  @override
  State<TypewriterText> createState() => TypewriterTextState();
}

class TypewriterTextState extends State<TypewriterText> {
  Timer? _timer;
  int _visible = 0;
  int _generation = 0;
  bool _skipped = false;
  bool _lastDisabled = false;

  void skip() {
    _skipped = true;
    _timer?.cancel();
    _timer = null;
    if (mounted) setState(() => _visible = widget.text.length);
  }

  void _start() {
    _timer?.cancel();
    final int gen = ++_generation;
    _visible = 0;
    _skipped = false;
    _lastDisabled = AppConfig.disableTypewriter;
    if (_lastDisabled) {
      _visible = widget.text.length;
      if (mounted) setState(() {});
      return;
    }
    final int intervalMs = math.max(1, 1000 ~/ AppConfig.typewriterCps);
    _timer = Timer.periodic(Duration(milliseconds: intervalMs), (Timer t) {
      if (gen != _generation || !mounted) {
        t.cancel();
        return;
      }
      if (_visible >= widget.text.length) {
        t.cancel();
        widget.onFinished?.call();
        return;
      }
      setState(() => _visible++);
    });
  }

  /// 设置页改开关后由父级 rebuild 触发；从全显切回逐字时重新播当前这句。
  void _syncFlag() {
    final bool now = AppConfig.disableTypewriter;
    if (now == _lastDisabled) return;
    _lastDisabled = now;
    if (now) {
      _timer?.cancel();
      _timer = null;
      _visible = widget.text.length;
      if (mounted) setState(() {});
    } else {
      _start();
      if (mounted) setState(() {});
    }
  }

  @override
  void initState() {
    super.initState();
    _start();
  }

  @override
  void didUpdateWidget(TypewriterText old) {
    super.didUpdateWidget(old);
    if (old.text == widget.text) {
      _syncFlag();
      return;
    }
    if (_skipped && widget.text.startsWith(old.text)) {
      _visible = widget.text.length;
      if (mounted) setState(() {});
      return;
    }
    _start();
  }

  @override
  void dispose() {
    _generation++;
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final int n = math.min(_visible, widget.text.length);
    return Text(
      widget.text.substring(0, n),
      style: TextStyle(
        color: GalPalette.of(context).text,
        fontSize: 16,
        height: 1.5,
      ),
    );
  }
}
