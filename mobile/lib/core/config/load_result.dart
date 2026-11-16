/// 插件真实加载结果的判定（纯 Dart，无插件依赖，便于单测）。
///
/// `flutter_live2d` 的 `Live2DViewController.loadModel` 返回 `Future<bool>`：
/// * `true`  = 原生 Cubism 侧加载成功；
/// * `false` = 原生侧拒绝了模型，**Future 正常完成、不抛异常**，错误只写在
///   `controller.value.lastError`（code = `LOAD_FAILED`）。
///
/// 旧实现只 `await` 了这个 Future，把「没抛异常」等同于「加载成功」，于是
/// 原生侧明明返回了 false，Dart 侧照样置 `ready = true`、撤掉占位层 ——
/// 这就是「检测通过 / 显示已就绪 / 中间占位也没了 / 却看不到模型」的根因。
/// 文件存在性自检只能证明文件在，证明不了 `.moc3` 能被 Cubism Core 解析。
class LoadVerdict {
  const LoadVerdict(this.ok, this.error);

  final bool ok;
  /// 原生侧给出的错误码 / 描述，成功时为空串。
  final String error;
}

class LoadResultInterpreter {
  LoadResultInterpreter._();

  static LoadVerdict interpret({
    required dynamic futureValue,
    required bool? stateIsLoaded,
    required String stateError,
  }) {
    // 1. 新版本：Future<bool> 的 false 是明确的失败信号，优先级最高。
    if (futureValue is bool && !futureValue) {
      return LoadVerdict(
        false,
        stateError.isNotEmpty ? stateError : 'LOAD_FAILED',
      );
    }
    // 2. 即使返回 true，也要和 controller 的响应式状态交叉验证：
    //    有些失败会异步写进 lastError，或 isLoaded 仍为 false。
    if (stateError.isNotEmpty) return LoadVerdict(false, stateError);
    if (stateIsLoaded == false) {
      return const LoadVerdict(false, '模型状态未确认（isLoaded=false）');
    }
    // 3. 明确成功：true 且状态无错误，或老版本返回 void 但状态显示已加载。
    if (futureValue is bool && futureValue) return const LoadVerdict(true, '');
    if (stateIsLoaded == true) return const LoadVerdict(true, '');
    // 4. 返回 void / 非 bool 且读不到状态：宁可报「未确认」，绝不谎报就绪。
    return const LoadVerdict(false, '插件未返回加载结果，无法确认模型已渲染');
  }

  /// 把错误整理成占位层能显示的一行原因。
  static String failureText(String error, {bool threw = false}) {
    final String base = error.isEmpty ? '原生侧未确认加载结果' : error;
    return '模型加载未通过${threw ? '（调用异常）' : ''}：$base · '
        '文件齐全不代表模型可解析，请确认 .moc3 与入口 .model3.json 属于同一套模型、'
        '纹理是插件支持的格式，且 Cubism 版本在插件支持范围内';
  }
}
