import 'dart:async';

import 'package:flutter/material.dart';

import '../../app/gal_palette.dart';
import '../../app/motion.dart';
import '../../app/stage_scope.dart';
import '../../app/stage_session.dart';
import '../../core/config/app_config.dart';
import '../common/draggable_panel.dart';

/// 打字 + 语音按钮。
///
/// * 语音：点一下开始 / 再点一下停止，与按住说话并存；
/// * 可水平拖动到右侧隐藏成「←」箭头，隐藏即静态省电，点箭头恢复；
/// * Live2D 置顶浮窗模式下默认收成右侧小胶囊（不遮挡），点键盘展开即可输入；
/// * 提交走 `session.submitText` 的防抖合并 + 相邻去重。
class InputBar extends StatefulWidget {
  const InputBar({super.key});

  @override
  State<InputBar> createState() => _InputBarState();
}

class _InputBarState extends State<InputBar> {
  final TextEditingController _controller = TextEditingController();
  final FocusNode _focus = FocusNode();
  Timer? _lockTimer;
  bool _locked = false;
  bool _expanded = false;
  StageSession? _session;

  void _send([String? preset]) {
    if (_locked) return;
    final String text = (preset ?? _controller.text).trim();
    if (text.isEmpty || text.length > AppConfig.maxTextLength) return;
    final TextEditingValue value = _controller.value;
    if (!value.composing.isCollapsed) return;
    _session?.submitText(text);
    _controller.clear();
    _locked = true;
    _lockTimer?.cancel();
    _lockTimer = Timer(const Duration(milliseconds: 400), () {
      _locked = false;
      if (mounted) setState(() {});
    });
  }

  void _expand() {
    setState(() => _expanded = true);
    // 等一帧让 TextField 挂上树再请求焦点。
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _focus.requestFocus();
    });
  }

  @override
  void dispose() {
    _lockTimer?.cancel();
    _lockTimer = null;
    _controller.dispose();
    _focus.dispose();
    _session = null;
    super.dispose();
  }

  Widget _voiceButton(StageSession session, GalPaletteData p) {
    return GestureDetector(
      onTap: () => session.toggleVoice(),
      onLongPressStart: (_) => session.startVoice(),
      onLongPressEnd: (_) => session.stopVoice(),
      child: ValueListenableBuilder<bool>(
        valueListenable: session.recording,
        builder: (_, bool on, _) => AnimatedContainer(
          duration: Motion.short,
          width: 42,
          height: 42,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: on ? p.offline.withValues(alpha: .85) : p.cardAlt,
            border: Border.all(
              color: on ? p.offline : p.border,
              width: on ? 2 : 1,
            ),
            boxShadow: on
                ? <BoxShadow>[BoxShadow(color: p.glow, blurRadius: 12)]
                : null,
          ),
          child: Icon(on ? Icons.mic : Icons.mic_none, color: p.text, size: 20),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final StageSession session = StageScope.of(context);
    _session = session;
    final GalPaletteData p = GalPalette.of(context);
    return ValueListenableBuilder<bool>(
      valueListenable: session.overlayOn,
      builder: (BuildContext context, bool overlay, Widget? _) {
        final bool compact = overlay && !_expanded;
        return DraggablePanel(
          panelId: 'input',
          onHiddenChanged: session.setPanelHidden,
          alignment: compact ? Alignment.bottomRight : Alignment.bottomCenter,
          widthFactor: compact ? 0.46 : 1.0,
          child: SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 4, 12, 8),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  ValueListenableBuilder<bool>(
                    valueListenable: session.recording,
                    builder: (_, bool on, _) => AnimatedOpacity(
                      opacity: on ? 1 : 0,
                      duration: Motion.short,
                      child: Padding(
                        padding: const EdgeInsets.only(bottom: 4),
                        child: Text(
                          on
                              ? '● 录音中 · 点一下停止 / 松手停止 · ${session.asrEngineLabel}'
                              : '',
                          style: TextStyle(color: p.busy, fontSize: 10),
                        ),
                      ),
                    ),
                  ),
                  if (compact)
                    Row(
                      mainAxisAlignment: MainAxisAlignment.end,
                      mainAxisSize: MainAxisSize.min,
                      children: <Widget>[
                        Tooltip(
                          message: '向右拖动可收起 · 自动静态省电',
                          child: Icon(
                            Icons.drag_indicator,
                            color: p.textFaint,
                            size: 14,
                          ),
                        ),
                        _voiceButton(session, p),
                        const SizedBox(width: 6),
                        IconButton(
                          icon: Icon(Icons.keyboard, color: p.accent, size: 20),
                          tooltip: '展开输入框（置顶时也能打字）',
                          onPressed: _expand,
                        ),
                      ],
                    )
                  else
                    Row(
                      children: <Widget>[
                        Expanded(
                          child: TextField(
                            controller: _controller,
                            focusNode: _focus,
                            minLines: 1,
                            maxLines: 3,
                            style: TextStyle(color: p.text, fontSize: 14),
                            decoration: InputDecoration(
                              hintText: '说点什么…',
                              hintStyle: TextStyle(color: p.textFaint),
                              filled: true,
                              fillColor: p.dialog.withValues(alpha: .88),
                              border: OutlineInputBorder(
                                borderRadius: BorderRadius.circular(20),
                                borderSide: BorderSide(color: p.border),
                              ),
                              enabledBorder: OutlineInputBorder(
                                borderRadius: BorderRadius.circular(20),
                                borderSide: BorderSide(color: p.border),
                              ),
                              contentPadding: const EdgeInsets.symmetric(
                                horizontal: 14,
                                vertical: 8,
                              ),
                            ),
                            onSubmitted: (String _) => _send(),
                          ),
                        ),
                        const SizedBox(width: 8),
                        _voiceButton(session, p),
                        const SizedBox(width: 8),
                        IconButton(
                          icon: Icon(Icons.send, color: p.accent),
                          onPressed: () => _send(),
                        ),
                        if (overlay)
                          IconButton(
                            icon: Icon(
                              Icons.expand_more,
                              color: p.textDim,
                              size: 18,
                            ),
                            tooltip: '收成小胶囊（不遮挡）',
                            onPressed: () => setState(() => _expanded = false),
                          ),
                      ],
                    ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}
