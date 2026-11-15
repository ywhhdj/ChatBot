import 'package:flutter/material.dart';

/// 设定面板分区卡片（组件层通用件）。
class SectionCard extends StatelessWidget {
  const SectionCard({super.key, required this.title, required this.children});

  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF1B1026).withOpacity(.92),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: Colors.white12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(title,
              style: const TextStyle(
                  color: Color(0xFFE9B8FF),
                  fontSize: 13,
                  fontWeight: FontWeight.bold)),
          const SizedBox(height: 10),
          ...children,
        ],
      ),
    );
  }
}
