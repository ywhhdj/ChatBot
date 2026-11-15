import 'package:flutter/foundation.dart';

/// debug/ 目录里唯一允许被业务层 import 的文件。
/// 只含编译期常量：release 下恒为 false，AOT tree-shaking 会把其余 debug/* 整体摇掉。
const bool kStageDebug =
    !kReleaseMode && (kDebugMode || bool.fromEnvironment('STAGE_DEBUG'));

/// 帧级调试元数据（更啰嗦），同样编译期常量。
const bool kStageFrameMeta =
    kStageDebug && bool.fromEnvironment('STAGE_FRAME_META');
