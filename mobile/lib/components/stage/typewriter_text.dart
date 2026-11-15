import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../core/config/app_config.dart';

/// 打字机：单 Timer + generation 令牌（U39），Skip 后 delta 续写不再重启（U40）。
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

  @override
  void initState() {
    super.initState();
    _start();
  }

  @override
  void didUpdateWidget(TypewriterText old) {
    super.didUpdateWidget(old);
    if (old.text == widget.text) return;
    if (_skipped && widget.text.startsWith(old.text)) {
      // 跳过后的流式续写：直接全显，不重新逐字。
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
      style: const TextStyle(color: Colors.white, fontSize: 16, height: 1.5),
    );
  }
}
