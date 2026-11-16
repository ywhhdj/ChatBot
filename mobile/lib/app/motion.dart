import 'package:flutter/material.dart';

import '../core/config/app_config.dart';

/// 「减少动画」统一开关（设定 → 省电）。
///
/// 只关**界面切换类动画**（页面转场、分区滑动、卡片/透明度过渡、逐字机、
/// 面板折叠）；Live2D 立绘演出与舞台帧泵属于 live2d 本体，始终保留。
class Motion {
  Motion._();

  static bool get off => AppConfig.reduceAnimations;

  static Duration ms(int milliseconds) =>
      off ? Duration.zero : Duration(milliseconds: milliseconds);

  static Duration get short => ms(180);
  static Duration get medium => ms(260);
  static Duration get long => ms(420);

  static Curve get curve => off ? Curves.linear : Curves.easeOutCubic;

  /// 页面转场：减少动画时零时长 + 不做位移。
  static Duration get page => ms(260);
}
