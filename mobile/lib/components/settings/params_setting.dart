import 'package:flutter/material.dart';

import '../../app/gal_palette.dart';
import '../../app/stage_session.dart';
import '../../core/config/app_config.dart';
import '../../services/storage/prefs.dart';
import '../common/section_card.dart';

/// 演出 / 性能参数：全部可在手机上调，变更即生效、松手即持久化。
///
/// 性能：每个滑杆是独立的 StatefulWidget，拖动时只重建自己；
/// 旧实现每帧 setState 会重建整张设定面板（十几个 Slider + Switch），低档机掉帧。
class ParamsSetting extends StatefulWidget {
  const ParamsSetting({super.key, required this.session});

  final StageSession session;

  @override
  State<ParamsSetting> createState() => _ParamsSettingState();
}

class _ParamsSettingState extends State<ParamsSetting> {
  Future<void> _commit() async {
    Prefs.scheduleSave();
    widget.session.applyParams();
  }

  Widget _switch(BuildContext context, String label, bool value, ValueChanged<bool> onChanged) {
    return SwitchListTile(
      contentPadding: EdgeInsets.zero,
      dense: true,
      activeColor: GalPalette.of(context).accent,
      title: Text(label,
          style: TextStyle(color: GalPalette.of(context).textDim, fontSize: 11)),
      value: value,
      onChanged: (bool v) {
        onChanged(v);
        setState(() {});
        _commit();
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return SectionCard(
      title: '演出 / 性能参数',
      children: <Widget>[
        Padding(
          padding: EdgeInsets.only(bottom: 6),
          child: Text('目标帧率、实时帧率显示、后台省电与置顶浮窗在「省电」分区。',
              style: TextStyle(color: GalPalette.of(context).textFaint, fontSize: 10)),
        ),
        _ParamSlider(
          label: '右弹触发速度',
          value: AppConfig.swipeRightVelocity,
          min: 300,
          max: 1600,
          divisions: 13,
          onChanged: (double v) => AppConfig.swipeRightVelocity = v,
          onCommit: _commit,
        ),
        _ParamSlider(
          label: '右弹最小距离',
          value: AppConfig.swipeMinDistance,
          min: 20,
          max: 160,
          divisions: 14,
          onChanged: (double v) => AppConfig.swipeMinDistance = v,
          onCommit: _commit,
        ),
        _ParamSlider(
          label: '姿态发送频率',
          value: AppConfig.poseSendHz.toDouble(),
          min: 6,
          max: 30,
          divisions: 4,
          unit: 'Hz',
          onChanged: (double v) => AppConfig.poseSendHz = v.round(),
          onCommit: _commit,
        ),
        _ParamSlider(
          label: '姿态死区（越小越灵敏）',
          value: AppConfig.poseDeadZoneDeg,
          min: 0,
          max: 6,
          divisions: 12,
          unit: '°',
          onChanged: (double v) => AppConfig.poseDeadZoneDeg = v,
          onCommit: _commit,
        ),
        _ParamSlider(
          label: '姿态低通（越小越稳）',
          value: AppConfig.poseLowPassK,
          min: 0.05,
          max: 0.6,
          divisions: 11,
          decimals: 2,
          onChanged: (double v) => AppConfig.poseLowPassK = v,
          onCommit: _commit,
        ),
        _ParamSlider(
          label: '侧头回来延时',
          value: AppConfig.peekDelayMs.toDouble(),
          min: 400,
          max: 3000,
          divisions: 13,
          unit: 'ms',
          onChanged: (double v) => AppConfig.peekDelayMs = v.round(),
          onCommit: _commit,
        ),
        _ParamSlider(
          label: '侧头停留时长',
          value: AppConfig.peekHoldMs.toDouble(),
          min: 200,
          max: 2500,
          divisions: 11,
          unit: 'ms',
          onChanged: (double v) => AppConfig.peekHoldMs = v.round(),
          onCommit: _commit,
        ),
        _ParamSlider(
          label: '甩出动画时长',
          value: AppConfig.flingDurationMs.toDouble(),
          min: 200,
          max: 900,
          divisions: 14,
          unit: 'ms',
          onChanged: (double v) => AppConfig.flingDurationMs = v.round(),
          onCommit: _commit,
        ),
        _ParamSlider(
          label: '回场动画时长',
          value: AppConfig.returnDurationMs.toDouble(),
          min: 200,
          max: 1200,
          divisions: 10,
          unit: 'ms',
          onChanged: (double v) => AppConfig.returnDurationMs = v.round(),
          onCommit: _commit,
        ),
        _ParamSlider(
          label: '打字机速度',
          value: AppConfig.typewriterCps.toDouble(),
          min: 10,
          max: 60,
          divisions: 10,
          unit: 'cps',
          onChanged: (double v) => AppConfig.typewriterCps = v.round(),
          onCommit: _commit,
        ),
        _ParamSlider(
          label: '双击转向幅度',
          value: AppConfig.turnStepDeg,
          min: 6,
          max: 30,
          divisions: 12,
          unit: '°',
          onChanged: (double v) => AppConfig.turnStepDeg = v,
          onCommit: _commit,
        ),
        _ParamSlider(
          label: '触发冷却',
          value: AppConfig.triggerCooldownMs.toDouble(),
          min: 500,
          max: 5000,
          divisions: 9,
          unit: 'ms',
          onChanged: (double v) => AppConfig.triggerCooldownMs = v.round(),
          onCommit: _commit,
        ),
        _ParamSlider(
          label: '最大重连次数',
          value: AppConfig.maxReconnectAttempts.toDouble(),
          min: 1,
          max: 20,
          divisions: 19,
          unit: '次',
          onChanged: (double v) => AppConfig.maxReconnectAttempts = v.round(),
          onCommit: _commit,
        ),
        _switch(context, 
          '打字实时镜像到电脑端（chat 已转发，默认关避免重复）',
          AppConfig.mirrorTextInput,
          (bool v) => AppConfig.mirrorTextInput = v,
        ),
        _switch(context, 
          'ASR 文本镜像到电脑端（自动发送关时生效）',
          AppConfig.mirrorAsrText,
          (bool v) => AppConfig.mirrorAsrText = v,
        ),
        const SizedBox(height: 4),
        Align(
          alignment: Alignment.centerRight,
          child: TextButton.icon(
            onPressed: () async {
              AppConfig.restoreDefaults();
              await _commit();
              if (mounted) setState(() {});
            },
            icon: const Icon(Icons.restore, size: 14),
            label: const Text('恢复默认', style: TextStyle(fontSize: 11)),
          ),
        ),
      ],
    );
  }
}

/// 单条滑杆：拖动只 setState 自己，松手（onChangeEnd）才写盘并通知舞台。
class _ParamSlider extends StatefulWidget {
  const _ParamSlider({
    required this.label,
    required this.value,
    required this.min,
    required this.max,
    required this.divisions,
    required this.onChanged,
    required this.onCommit,
    this.unit = '',
    this.decimals = 1,
  });

  final String label;
  final double value;
  final double min;
  final double max;
  final int divisions;
  final String unit;
  final int decimals;
  final ValueChanged<double> onChanged;
  final Future<void> Function() onCommit;

  @override
  State<_ParamSlider> createState() => _ParamSliderState();
}

class _ParamSliderState extends State<_ParamSlider> {
  late double _value = widget.value.clamp(widget.min, widget.max).toDouble();

  @override
  void didUpdateWidget(_ParamSlider old) {
    super.didUpdateWidget(old);
    // 「恢复默认」后父级重建，滑杆要同步回默认值。
    if (old.value != widget.value) {
      _value = widget.value.clamp(widget.min, widget.max).toDouble();
    }
  }

  String get _display =>
      '${_value.toStringAsFixed(widget.decimals)}${widget.unit}';

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Row(
            children: <Widget>[
              Expanded(
                child: Text(widget.label,
                    style: TextStyle(
                        color: GalPalette.of(context).textDim, fontSize: 11)),
              ),
              Text(_display,
                  style: TextStyle(
                      color: GalPalette.of(context).accent, fontSize: 11)),
            ],
          ),
          SliderTheme(
            data: SliderTheme.of(context).copyWith(
              activeTrackColor: GalPalette.of(context).accent,
              inactiveTrackColor: GalPalette.of(context).border,
              thumbColor: GalPalette.of(context).accent,
              overlayColor: const Color(0x337FD4FF),
              valueIndicatorColor: GalPalette.of(context).cardAlt,
            ),
            child: Slider(
              min: widget.min,
              max: widget.max,
              divisions: widget.divisions,
              value: _value,
              onChanged: (double v) {
                setState(() => _value = v);
                widget.onChanged(v);
              },
              onChangeEnd: (double _) => widget.onCommit(),
            ),
          ),
        ],
      ),
    );
  }
}
