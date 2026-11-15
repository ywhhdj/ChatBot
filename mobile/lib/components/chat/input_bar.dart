import 'dart:async';

import 'package:flutter/material.dart';

import '../../app/stage_scope.dart';
import '../../core/config/app_config.dart';

/// 打字 + 按住说话。composing 期间回车不发送，空/超长不发
class InputBar extends StatefulWidget {
  const InputBar({super.key});

  @override
  State<InputBar> createState() => _InputBarState();
}

class _InputBarState extends State<InputBar> {
  final TextEditingController _controller = TextEditingController();
  bool _locked = false;   // 识别自动发送与手动点发送去重
  bool _holding = false;

  void _send([String? preset]) {
    if (_locked) return;
    final String text = (preset ?? _controller.text).trim();
    if (text.isEmpty || text.length > AppConfig.maxTextLength) return;
    final TextEditingValue value = _controller.value;
    if (!value.composing.isCollapsed) return;
    StageScope.of(context).sendText(text);
    _controller.clear();
    _locked = true;
    Timer(const Duration(milliseconds: 500), () {
      if (mounted) setState(() => _locked = false);
      _locked = false;
    });
  }

  Future<void> _startVoice() async {
    if (_holding) return;
    _holding = true;
    await StageScope.of(context).voice.start();
  }

  Future<void> _stopVoice() async {
    if (!_holding) return;
    _holding = false;
    await StageScope.of(context).voice.stop();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 4, 12, 8),
        child: Row(
          children: <Widget>[
            Expanded(
              child: TextField(
                controller: _controller,
                minLines: 1,
                maxLines: 3,
                style: const TextStyle(color: Colors.white, fontSize: 14),
                decoration: InputDecoration(
                  hintText: '说点什么…',
                  hintStyle: const TextStyle(color: Colors.white38),
                  filled: true,
                  fillColor: Colors.black54,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(20),
                    borderSide: BorderSide.none,
                  ),
                  contentPadding:
                      const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                ),
                onSubmitted: (String _) => _send(),
              ),
            ),
            const SizedBox(width: 8),
            GestureDetector(
              onLongPressStart: (_) => _startVoice(),
              onLongPressEnd: (_) => _stopVoice(),
              child: ValueListenableBuilder<bool>(
                valueListenable: StageScope.of(context).recording,
                builder: (_, bool on, _) => CircleAvatar(
                  backgroundColor: on ? Colors.pinkAccent : Colors.white24,
                  child: Icon(on ? Icons.mic : Icons.mic_none,
                      color: Colors.white, size: 20),
                ),
              ),
            ),
            const SizedBox(width: 8),
            IconButton(
              icon: const Icon(Icons.send, color: Color(0xFFE9B8FF)),
              onPressed: () => _send(),
            ),
          ],
        ),
      ),
    );
  }
}
