import AVFoundation
import Flutter
import Speech
import UIKit

/// 系统内置语音识别（SFSpeechRecognizer + AVAudioEngine）。
/// 无电脑端 / 离线时由 Dart 侧 AsrMode.auto 自动回退到这里；
/// 不新增任何 Pod 依赖。Info.plist 需声明 NSSpeechRecognitionUsageDescription。
public class SystemAsrChannel: NSObject, FlutterPlugin {
  private static let channelName = "ar_live2d_agent/system_asr"

  private var channel: FlutterMethodChannel?
  private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "zh-CN"))
  private let engine = AVAudioEngine()
  private var request: SFSpeechAudioBufferRecognitionRequest?
  private var task: SFSpeechRecognitionTask?
  private var lastText = ""

  public static func register(with registrar: FlutterPluginRegistrar) {
    let channel = FlutterMethodChannel(
      name: channelName,
      binaryMessenger: registrar.messenger())
    let instance = SystemAsrChannel()
    instance.channel = channel
    registrar.addMethodCallDelegate(instance, channel: channel)
  }

  public func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    switch call.method {
    case "available":
      let status = SFSpeechRecognizer.authorizationStatus()
      let usable = recognizer != nil && status != .denied && status != .restricted
      result(usable)
    case "start":
      start { ok in result(ok ? nil : FlutterError(
        code: "ASR_UNAVAILABLE",
        message: "系统识别不可用，请重试",
        details: nil)) }
    case "stop":
      stop()
      result(nil)
    default:
      result(FlutterMethodNotImplemented)
    }
  }

  private func start(completion: @escaping (Bool) -> Void) {
    SFSpeechRecognizer.requestAuthorization { [weak self] status in
      guard let self = self else { return }
      DispatchQueue.main.async {
        guard status == .authorized, self.recognizer != nil else {
          self.emitError("语音识别未授权，请重试")
          completion(false)
          return
        }
        self.stop()
        self.lastText = ""
        do {
          let session = AVAudioSession.sharedInstance()
          try session.setCategory(.record, mode: .measurement, options: .duckOthers)
          try session.setActive(true, options: .notifyOthersOnDeactivation)

          let req = SFSpeechAudioBufferRecognitionRequest()
          req.shouldReportPartialResults = true
          self.request = req

          let input = self.engine.inputNode
          let format = input.outputFormat(forBus: 0)
          input.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
            req.append(buffer)
          }
          self.engine.prepare()
          try self.engine.start()

          self.task = self.recognizer?.recognitionTask(with: req) { [weak self] res, error in
            guard let self = self else { return }
            if let text = res?.bestTranscription.formattedString, !text.isEmpty {
              self.emitText(text)
            }
            if let error = error {
              self.emitError("系统识别失败：\(error.localizedDescription)")
            }
          }
          completion(true)
        } catch {
          self.emitError("启动失败：\(error.localizedDescription)")
          completion(false)
        }
      }
    }
  }

  private func stop() {
    if engine.isRunning {
      engine.stop()
      engine.inputNode.removeTap(onBus: 0)
    }
    request?.endAudio()
    task?.cancel()
    task = nil
    request = nil
    try? AVAudioSession.sharedInstance().setActive(false)
  }

  private func emitText(_ text: String) {
    let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !t.isEmpty, t != lastText else { return }
    lastText = t
    DispatchQueue.main.async {
      self.channel?.invokeMethod("onText", arguments: ["text": t])
    }
  }

  private func emitError(_ message: String) {
    DispatchQueue.main.async {
      self.channel?.invokeMethod("onError", arguments: ["message": message])
    }
  }
}
