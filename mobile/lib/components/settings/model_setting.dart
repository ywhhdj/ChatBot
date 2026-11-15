import 'package:ar_live2d_agent/app/stage_session.dart';
import 'package:flutter/material.dart';

import '../../app/stage_scope.dart';
import '../../core/config/app_config.dart';
import '../../core/config/model_config.dart';
import '../common/section_card.dart';

/// 模型与演出参数（S3.2 / S6.4）。
class ModelSetting extends StatefulWidget {
  const ModelSetting({super.key});

  @override
  State<ModelSetting> createState() => _ModelSettingState();
}

class _ModelSettingState extends State<ModelSetting> {
  @override
  Widget build(BuildContext context) {
    final StageSession session = StageScope.of(context);
    return SectionCard(
      title: 'Live2D 模型 / 演出',
      children: <Widget>[
        DropdownButton<String>(
          value: AppConfig.activeModelId,
          isExpanded: true,
          dropdownColor: const Color(0xFF241634),
          style: const TextStyle(color: Colors.white, fontSize: 13),
          items: <DropdownMenuItem<String>>[
            for (final ModelConfig m in ModelConfig.available)
              DropdownMenuItem<String>(value: m.id, child: Text(m.name)),
          ],
          onChanged: (String? id) async {
            if (id == null) return;
            final ModelConfig m = ModelConfig.byId(id);
            await session.changeModel(id, m.path);
            if (mounted) setState(() {});
          },
        ),
        const SizedBox(height: 8),
        DropdownButton<StageQuality>(
          value: AppConfig.quality,
          isExpanded: true,
          dropdownColor: const Color(0xFF241634),
          style: const TextStyle(color: Colors.white, fontSize: 13),
          items: <DropdownMenuItem<StageQuality>>[
            for (final StageQuality q in StageQuality.values)
              DropdownMenuItem<StageQuality>(value: q, child: Text(q.name)),
          ],
          onChanged: (StageQuality? q) {
            if (q == null) return;
            setState(() => AppConfig.quality = q);
          },
        ),
        const SizedBox(height: 8),
        Text('右弹阈值 ${AppConfig.swipeRightVelocity.toInt()} · '
            '侧头延时 ${AppConfig.peekDelay.inMilliseconds}ms',
            style: const TextStyle(color: Colors.white54, fontSize: 11)),
        Text(session.live2d.degradationReason ?? '模型已就绪',
            style: const TextStyle(color: Colors.white38, fontSize: 11)),
      ],
    );
  }
}
