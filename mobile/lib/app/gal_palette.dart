import 'package:flutter/material.dart';

/// 三套 galgame 色系：黑夜 / 米白 / 蓝色（默认蓝）
enum GalScheme { night, cream, blue }

/// 一套完整配色（实例数据，可运行时切换；不能用于 const 上下文）。
class GalPaletteData {
  const GalPaletteData({
    required this.name,
    required this.brightness,
    required this.bgTop,
    required this.bgBottom,
    required this.scaffold,
    required this.sheet,
    required this.card,
    required this.cardAlt,
    required this.dialog,
    required this.bubbleMine,
    required this.characterTop,
    required this.characterBottom,
    required this.border,
    required this.borderSoft,
    required this.accent,
    required this.accentSoft,
    required this.text,
    required this.textDim,
    required this.textFaint,
    required this.online,
    required this.busy,
    required this.offline,
    required this.scanFrame,
    required this.glow,
    required this.characterA,
    required this.characterB,
  });

  final String name;
  final Brightness brightness;
  final Color bgTop;
  final Color bgBottom;
  final Color scaffold;
  final Color sheet;
  final Color card;
  final Color cardAlt;
  final Color dialog;
  final Color bubbleMine;
  final Color characterTop;
  final Color characterBottom;
  final Color border;
  final Color borderSoft;
  final Color accent;
  final Color accentSoft;
  final Color text;
  final Color textDim;
  final Color textFaint;
  final Color online;
  final Color busy;
  final Color offline;
  final Color scanFrame;
  final Color glow;
  final Color characterA;
  final Color characterB;

  LinearGradient get background => LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: <Color>[bgTop, bgBottom],
      );

  LinearGradient get character => LinearGradient(
        begin: Alignment.bottomCenter,
        end: Alignment.topCenter,
        colors: <Color>[characterA, characterB],
      );

  ThemeData theme() => ThemeData(
        useMaterial3: true,
        brightness: brightness,
        colorScheme: ColorScheme.fromSeed(
          seedColor: accent,
          brightness: brightness,
        ).copyWith(
          primary: accent,
          secondary: accentSoft,
          surface: sheet,
          onSurface: text,
        ),
        scaffoldBackgroundColor: scaffold,
        canvasColor: scaffold,
        dividerColor: borderSoft,
        iconTheme: IconThemeData(color: accent, size: 20),
        textTheme: TextTheme(
          bodyMedium: TextStyle(color: text),
          bodySmall: TextStyle(color: textDim),
          titleMedium: TextStyle(color: text),
        ), dialogTheme: DialogThemeData(backgroundColor: dialog),
      );
}

const GalPaletteData kBluePalette = GalPaletteData(
  name: '蓝色夜色',
  brightness: Brightness.dark,
  bgTop: Color(0xFF0B1B33),
  bgBottom: Color(0xFF040A16),
  scaffold: Color(0xFF061225),
  sheet: Color(0xFF0A1730),
  card: Color(0xFF102544),
  cardAlt: Color(0xFF16335C),
  dialog: Color(0xFF0A1B36),
  bubbleMine: Color(0xFF1C4C7C),
  characterTop: Color(0xFF1B4E86),
  characterBottom: Color(0xFF08182E),
  border: Color(0xFF2C5A8C),
  borderSoft: Color(0x332C5A8C),
  accent: Color(0xFF7FD4FF),
  accentSoft: Color(0xFF4FA8E0),
  text: Color(0xFFEAF5FF),
  textDim: Color(0xFF9DBBD8),
  textFaint: Color(0xFF5D82A8),
  online: Color(0xFF5BE7C4),
  busy: Color(0xFFFFC46B),
  offline: Color(0xFFFF7A9C),
  scanFrame: Color(0xFF7FD4FF),
  glow: Color(0x335BC8FF),
  characterA: Color(0x992B6DB0),
  characterB: Color(0x0A08182E),
);

const GalPaletteData kNightPalette = GalPaletteData(
  name: '纯黑夜色',
  brightness: Brightness.dark,
  bgTop: Color(0xFF0B0B10),
  bgBottom: Color(0xFF000000),
  scaffold: Color(0xFF08080C),
  sheet: Color(0xFF121219),
  card: Color(0xFF1A1A23),
  cardAlt: Color(0xFF262631),
  dialog: Color(0xFF101017),
  bubbleMine: Color(0xFF2A2A36),
  characterTop: Color(0xFF34353F),
  characterBottom: Color(0xFF08080C),
  border: Color(0xFF3B3C48),
  borderSoft: Color(0x333B3C48),
  accent: Color(0xFFB9C6D6),
  accentSoft: Color(0xFF8A99AA),
  text: Color(0xFFE8EAF0),
  textDim: Color(0xFFA8AEBC),
  textFaint: Color(0xFF6C7382),
  online: Color(0xFF7FE0B0),
  busy: Color(0xFFE8C07A),
  offline: Color(0xFFFF8FA8),
  scanFrame: Color(0xFFB9C6D6),
  glow: Color(0x33B9C6D6),
  characterA: Color(0x995A5D6B),
  characterB: Color(0x0A08080C),
);

const GalPaletteData kCreamPalette = GalPaletteData(
  name: '米白暖纸',
  brightness: Brightness.light,
  bgTop: Color(0xFFF7F1E6),
  bgBottom: Color(0xFFEDE3D2),
  scaffold: Color(0xFFF6EFE3),
  sheet: Color(0xFFFFFBF4),
  card: Color(0xFFF2E8D8),
  cardAlt: Color(0xFFE7D8C2),
  dialog: Color(0xFFFFFBF4),
  bubbleMine: Color(0xFFDCE7EE),
  characterTop: Color(0xFFC9D9E4),
  characterBottom: Color(0xFFF6EFE3),
  border: Color(0xFFD8C3A5),
  borderSoft: Color(0x33D8C3A5),
  accent: Color(0xFF3E6E9E),
  accentSoft: Color(0xFF6E9AC4),
  text: Color(0xFF2B2A28),
  textDim: Color(0xFF5E5A54),
  textFaint: Color(0xFF938C82),
  online: Color(0xFF2F9E77),
  busy: Color(0xFFC07A24),
  offline: Color(0xFFC2516E),
  scanFrame: Color(0xFF3E6E9E),
  glow: Color(0x333E6E9E),
  characterA: Color(0x99A9C4D8),
  characterB: Color(0x0AF6EFE3),
);

GalPaletteData paletteFor(GalScheme scheme) {
  switch (scheme) {
    case GalScheme.night:
      return kNightPalette;
    case GalScheme.cream:
      return kCreamPalette;
    case GalScheme.blue:
      return kBluePalette;
  }
}

/// 全局主题作用域：挂在 MaterialApp 外层。
/// 组件调用 `GalPalette.of(context)` 会建立依赖，切换色系时自动重建。
class GalThemeScope extends InheritedNotifier<ValueNotifier<GalScheme>> {
  const GalThemeScope({
    super.key,
    required ValueNotifier<GalScheme> scheme,
    required super.child,
  }) : super(notifier: scheme);

  static GalScheme? maybeSchemeOf(BuildContext context) => context
      .dependOnInheritedWidgetOfExactType<GalThemeScope>()
      ?.notifier
      ?.value;
}


class GalPalette {
  GalPalette._();

  static final ValueNotifier<GalScheme> scheme =
      ValueNotifier<GalScheme>(GalScheme.blue);

  static GalPaletteData get active => paletteFor(scheme.value);

  static GalPaletteData of(BuildContext context) =>
      paletteFor(GalThemeScope.maybeSchemeOf(context) ?? scheme.value);

  static ThemeData theme() => active.theme();
}
