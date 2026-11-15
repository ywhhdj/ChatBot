import 'package:flutter/material.dart';

/// 消息气泡：from='mobile' 时右对齐，PC 回复左对齐。
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
          color: mine ? const Color(0xFF4A2C60) : Colors.white12,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Text(text, style: const TextStyle(color: Colors.white, fontSize: 13)),
      ),
    );
  }
}
