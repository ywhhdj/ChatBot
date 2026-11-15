import 'package:flutter/material.dart';

/// Galgame 主题：深紫夜色 + 高对比对话框。
final ThemeData galgameTheme = ThemeData(
  useMaterial3: true,
  colorScheme: ColorScheme.fromSeed(
    seedColor: const Color(0xFF7B4B94),
    brightness: Brightness.dark,
  ),
  scaffoldBackgroundColor: const Color(0xFF140E1A),
);
