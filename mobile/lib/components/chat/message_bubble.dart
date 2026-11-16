import 'package:flutter/material.dart';

import '../../app/gal_palette.dart';

/// 消息气泡：from='mobile' 时右对齐，PC 回复左对齐（蓝色 galgame 配色）。
class MessageBubble extends StatelessWidget {
  const MessageBubble({super.key, required this.text, this.from = 'mobile'});

  final String text;
  final String from;

  @override
  Widget build(BuildContext context) {
    final bool mine = from == 'mobile';
    return Align(
      alignment: mine ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4, horizontal: 8),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: mine ? GalPalette.of(context).bubbleMine : GalPalette.of(context).card,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: GalPalette.of(context).borderSoft),
        ),
        child: Text(text,
            style: TextStyle(color: GalPalette.of(context).text, fontSize: 13)),
      ),
    );
  }
}
