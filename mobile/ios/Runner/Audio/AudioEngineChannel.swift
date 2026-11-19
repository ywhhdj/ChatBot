import AVFoundation
import Flutter
import UIKit

/// AVAudioEngine 采集，float -> PCM16 经 EventChannel 回传 Dart
/// 若设备 inputFormat 非 16kHz，由后端 ASR 侧兼容；生产可在此接 AVAudioConverter 重采样。
public class AudioEngineChannel: NSObject, FlutterPlugin, FlutterStreamHandler {
  private let engine = AVAudioEngine()
  private var sink: FlutterEventSink?
  private var running = false
  private let bus: AVAudioNodeBus = 0

  public static func register(with registrar: FlutterPluginRegistrar) {
    let method = FlutterMethodChannel(
      name: "ar_live2d_agent/audio",
      binaryMessenger: registrar.messenger()
    )
    let events = FlutterEventChannel(
      name: "ar_live2d_agent/audio_stream",
      binaryMessenger: registrar.messenger()
    )
    let instance = AudioEngineChannel()
    method.setMethodCallHandler(instance.handle)
    events.setStreamHandler(instance)
    NotificationCenter.default.addObserver(
      instance,
      selector: #selector(handleInterruption(_:)),
      name: AVAudioSession.interruptionNotification,
      object: AVAudioSession.sharedInstance()
    )
  }

  public func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    switch call.method {
    case "start":
      start()
      result(nil)
    case "stop":
      stop()
      result(nil)
    default:
      result(FlutterMethodNotImplemented)
    }
  }

  public func onListen(
    withArguments arguments: Any?, eventSink events: @escaping FlutterEventSink
  ) -> FlutterError? {
    sink = events
    return nil
  }

  public func onCancel(withArguments arguments: Any?) -> FlutterError? {
    sink = nil
    return nil
  }

  private func start() {
    guard !running else { return }
    let session = AVAudioSession.sharedInstance()
    do {
      try session.setCategory(.record, mode: .measurement, options: .duckOthers)
      try session.setActive(true, options: .notifyOthersOnDeactivation)
    } catch {
      sink?(FlutterError(code: "AUDIO_SESSION", message: "\(error)", details: nil))
      return
    }
    let input = engine.inputNode
    let format = input.outputFormat(forBus: bus)
    input.installTap(onBus: bus, bufferSize: 1024, format: format) {
      [weak self] buffer, _ in
      guard let self = self, self.running,
        let channel = buffer.floatChannelData?[0] else { return }
      let frames = Int(buffer.frameLength)
      var bytes = Data()
      for i in 0..<frames {
        let sample = Swift.max(-1.0, Swift.min(1.0, Double(channel[i])))
        var value = Int16(sample * 32767.0)
        withUnsafeBytes(of: &value) { bytes.append(contentsOf: $0) }
      }
      let typed = FlutterStandardTypedData(bytes: bytes)
      DispatchQueue.main.async { self.sink?(typed) }
    }
    do {
      try engine.start()
      running = true
    } catch {
      input.removeTap(onBus: bus)
      sink?(FlutterError(code: "ENGINE", message: "\(error)", details: nil))
    }
  }

  private func stop() {
    guard running else { return }
    running = false
    engine.inputNode.removeTap(onBus: bus)
    engine.stop()
    try? AVAudioSession.sharedInstance().setActive(false)
  }

  /// 来电 / 其他 App 打断时自动停录并回滚状态。
  @objc private func handleInterruption(_ note: Notification) {
    guard let raw = note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
      let type = AVAudioSession.InterruptionType(rawValue: raw) else { return }
    if type == .began {
      stop()
      DispatchQueue.main.async {
        self.sink?(FlutterError(
          code: "INTERRUPTED", 
          message: "录音被系统打断", details: nil
        ))
      }
    }
  }
}
