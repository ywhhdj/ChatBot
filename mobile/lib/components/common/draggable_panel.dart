import 'package:flutter/material.dart';

import '../../app/gal_palette.dart';
import '../../app/motion.dart';

/// 可水平拖动的面板壳：向右拖过阈值即「隐藏到右侧」，只剩一个左箭头；
/// 点箭头（或向左拖回来）即展开。展开/隐藏触发 `onHiddenChanged`，
/// 由 StageSession 汇总成「静态省电」状态。
///
/// * GestureDetector 只包住 `widthFactor` 指定的可见区域，不拦截舞台其它手势；
/// * `alignment` / `widthFactor` 让置顶浮窗模式把面板缩小靠右，避免遮挡；
/// * 减少动画时位移与显隐都是瞬时。
class DraggablePanel extends StatefulWidget {
  const DraggablePanel({
    super.key,
    required this.child,
    required this.panelId,
    required this.onHiddenChanged,
    this.enabled = true,
    this.edgeFraction = 0.34,
    this.initiallyHidden = false,
    this.alignment = Alignment.bottomCenter,
    this.widthFactor = 1.0,
  });

  final Widget child;
  final String panelId;
  final void Function(String id, bool hidden) onHiddenChanged;
  final bool enabled;
  final double edgeFraction;
  final bool initiallyHidden;
  final AlignmentGeometry alignment;
  final double widthFactor;

  @override
  State<DraggablePanel> createState() => _DraggablePanelState();
}

class _DraggablePanelState extends State<DraggablePanel> {
  double _dx = 0;
  late bool _hidden = widget.initiallyHidden;

  void _hide() {
    if (_hidden) return;
    setState(() {
      _hidden = true;
      _dx = 0;
    });
    widget.onHiddenChanged(widget.panelId, true);
  }

  void _show() {
    if (!_hidden) return;
    setState(() {
      _hidden = false;
      _dx = 0;
    });
    widget.onHiddenChanged(widget.panelId, false);
  }

  @override
  void didUpdateWidget(DraggablePanel old) {
    super.didUpdateWidget(old);
    if (!widget.enabled && _hidden) {
      _hidden = false;
      _dx = 0;
      widget.onHiddenChanged(widget.panelId, false);
    }
  }

  @override
  void dispose() {
    if (_hidden) {
      // 不能在 dispose 阶段同步通知：监听者可能正在 deactivate，
      // 触发 staticMode 变化会引出一轮非法 rebuild。延后到帧后并吞掉异常。
      final String id = widget.panelId;
      final void Function(String, bool) callback = widget.onHiddenChanged;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        try {
          callback(id, false);
        } catch (_) {}
      });
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final GalPaletteData p = GalPalette.of(context);
    if (_hidden) {
      return Align(
        alignment: Alignment.centerRight,
        child: GestureDetector(
          onTap: _show,
          onHorizontalDragEnd: (DragEndDetails d) {
            if (d.primaryVelocity != null && d.primaryVelocity! < -120) _show();
          },
          child: AnimatedContainer(
            duration: Motion.short,
            width: 30,
            height: 76,
            decoration: BoxDecoration(
              color: p.dialog.withValues(alpha: .86),
              borderRadius: const BorderRadius.horizontal(
                left: Radius.circular(14),
              ),
              border: Border.all(color: p.border),
            ),
            child: Icon(Icons.keyboard_arrow_left, color: p.accent, size: 20),
          ),
        ),
      );
    }

    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints c) {
        final double threshold = c.maxWidth * widget.edgeFraction;
        final double w = (c.maxWidth * widget.widthFactor).clamp(
          0.0,
          c.maxWidth,
        );
        return Align(
          alignment: widget.alignment,
          child: SizedBox(
            width: w,
            child: GestureDetector(
              behavior: HitTestBehavior.deferToChild,
              onHorizontalDragUpdate: widget.enabled
                  ? (DragUpdateDetails d) {
                      setState(
                        () => _dx = (_dx + d.delta.dx).clamp(0.0, c.maxWidth),
                      );
                    }
                  : null,
              onHorizontalDragEnd: widget.enabled
                  ? (DragEndDetails d) {
                      if (_dx >= threshold || (d.primaryVelocity ?? 0) > 600) {
                        _hide();
                      } else {
                        setState(() => _dx = 0);
                      }
                    }
                  : null,
              child: Transform.translate(
                offset: Offset(_dx, 0),
                child: widget.child,
              ),
            ),
          ),
        );
      },
    );
  }
}
