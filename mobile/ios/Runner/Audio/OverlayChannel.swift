import Flutter
import UIKit

/// iOS 不允许应用把视图浮在其他应用之上（无 SYSTEM_ALERT_WINDOW 对等能力）。
/// 该通道明确返回 unavailable，Dart 侧会提示用户并保留应用内低帧率后台演出；
/// 应用内的「缩小在右侧 + 右侧探头」由 StageView 自行实现。
public class OverlayChannel: NSObject, FlutterPlugin {
  private static let channelName = "ar_live2d_agent/overlay"

  public static func register(with registrar: FlutterPluginRegistrar) {
    let channel = FlutterMethodChannel(
      name: channelName,
      binaryMessenger: registrar.messenger())
    let instance = OverlayChannel()
    registrar.addMethodCallDelegate(instance, channel: channel)
  }

  public func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    switch call.method {
    case "available", "canDraw":
      result(false)
    case "start":
      result(false)
    case "stop", "updateAppearance":
      // 应用内演出由 Dart 侧负责，这里只是避免 MethodChannel 抛 notImplemented。
      result(nil)
    default:
      result(FlutterMethodNotImplemented)
    }
  }
}
