import 'package:flutter/material.dart';

import '../../app/gal_palette.dart';

/// 蓝色 galgame 风格空态 / 失败提示：无历史、模型未加载、离线时统一显示「请重试」。
class RetryHint extends StatelessWidget {
  const RetryHint({
    super.key,
    required this.title,
    this.detail,
    this.actionLabel = '请重试',
    this.onRetry,
    this.compact = false,
  });

  final String title;
  final String? detail;
  final String actionLabel;
  final VoidCallback? onRetry;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: EdgeInsets.symmetric(
        horizontal: compact ? 12 : 16,
        vertical: compact ? 10 : 18,
      ),
      decoration: BoxDecoration(
        color: GalPalette.of(context).dialog.withValues(alpha: 0.88),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: GalPalette.of(context).border, width: 1),
        boxShadow: const <BoxShadow>[
          BoxShadow(color: Color(0x335BC8FF), blurRadius: 16, spreadRadius: -8),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.center,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Text(
            title,
            textAlign: TextAlign.center,
            style: TextStyle(
              color: GalPalette.of(context).accent,
              fontSize: 13,
              letterSpacing: 1.4,
            ),
          ),
          if (detail != null) ...<Widget>[
            const SizedBox(height: 8),
            Text(
              detail!,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: GalPalette.of(context).textDim,
                fontSize: 11,
              ),
            ),
          ],
          if (onRetry != null) ...<Widget>[
            const SizedBox(height: 12),
            OutlinedButton.icon(
              style: OutlinedButton.styleFrom(
                foregroundColor: GalPalette.of(context).accent,
                side: BorderSide(color: GalPalette.of(context).border),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(20),
                ),
                padding: const EdgeInsets.symmetric(
                  horizontal: 18,
                  vertical: 8,
                ),
              ),
              onPressed: onRetry,
              icon: const Icon(Icons.refresh, size: 15),
              label: Text(actionLabel, style: const TextStyle(fontSize: 12)),
            ),
          ],
        ],
      ),
    );
  }
}
