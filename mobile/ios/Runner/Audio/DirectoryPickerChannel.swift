import Flutter
import MobileCoreServices
import UIKit
import UniformTypeIdentifiers

/// 系统底层目录选择器（UIDocumentPickerViewController .folder）。
///
/// `asCopy: false` 只关联目录，不复制、不导入任何模型文件；
/// 返回 security-scoped URL.path + 递归列出的模型文件（深度 2 / 上限 64）。
/// iOS 的安全作用域授权不跨进程持久保存，重启后如需访问请重新选择目录（路径已持久化）。
public class DirectoryPickerChannel: NSObject, FlutterPlugin, UIDocumentPickerDelegate {
  private static let channelName = "ar_live2d_agent/directory_picker"
  private static let exts = [".model3.json", ".model.json", ".moc3"]
  private static let maxDepth = 2
  private static let maxModels = 64
  private static let maxEntries = 2000
  private static let generatedPrefix = "__gal_compat_"

  private var channel: FlutterMethodChannel?
  private var pending: FlutterResult?

  public static func register(with registrar: FlutterPluginRegistrar) {
    let channel = FlutterMethodChannel(
      name: channelName,
      binaryMessenger: registrar.messenger())
    let instance = DirectoryPickerChannel()
    instance.channel = channel
    registrar.addMethodCallDelegate(instance, channel: channel)
  }

  public func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    guard call.method == "pick" else {
      result(FlutterMethodNotImplemented)
      return
    }
    guard pending == nil else {
      result(nil)
      return
    }
    pending = result

    let picker: UIDocumentPickerViewController
    if #available(iOS 14.0, *) {
      picker = UIDocumentPickerViewController(
        forOpeningContentTypes: [UTType.folder], asCopy: false)
    } else {
      picker = UIDocumentPickerViewController(
        documentTypes: [String(kUTTypeFolder)], in: .open)
    }
    picker.delegate = self
    picker.allowsMultipleSelection = false
    picker.shouldShowFileExtensions = true
    picker.modalPresentationStyle = .formSheet

    guard let root = Self.keyWindow()?.rootViewController else {
      finish(nil)
      return
    }
    DispatchQueue.main.async {
      root.present(picker, animated: true, completion: nil)
    }
  }

  private static func keyWindow() -> UIWindow? {
    UIApplication.shared.connectedScenes
      .compactMap { $0 as? UIWindowScene }
      .flatMap { $0.windows }
      .first { $0.isKeyWindow }
  }

  public func documentPicker(
    _ controller: UIDocumentPickerViewController,
    didPickDocumentsAt urls: [URL]
  ) {
    guard let url = urls.first else {
      finish(nil)
      return
    }
    let accessing = url.startAccessingSecurityScopedResource()
    defer {
      if accessing { url.stopAccessingSecurityScopedResource() }
    }
    let path = url.path
    var files: [String] = []
    var visited = 0
    listModels(path, depth: 0, visited: &visited, into: &files)
    let privateContainer = path.contains("/var/mobile/Containers/Data/Application/")
    let note = privateContainer
      ? "这是 App 自己的容器目录，里面的模型已由内置清单 / 物化副本加载过；请改选文件 App 里的模型目录（iOS 重启后需重新授权一次）"
      : "已关联系统目录（未复制文件）；iOS 重启后如需访问请重新选择一次目录"
    finish([
      "path": path,
      "uri": url.absoluteString,
      "display": url.lastPathComponent,
      "files": files,
      "note": note,
    ])
  }

  public func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
    finish(nil)
  }

  private func finish(_ value: Any?) {
    let r = pending
    pending = nil
    DispatchQueue.main.async { r?(value) }
  }

  private func isModel(_ name: String) -> Bool {
    let lower = name.lowercased()
    if lower.hasPrefix(Self.generatedPrefix) { return false }
    return Self.exts.contains { lower.hasSuffix($0) }
  }

  private func listModels(
    _ root: String,
    depth: Int,
    visited: inout Int,
    into out: inout [String]
  ) {
    guard depth <= Self.maxDepth, out.count < Self.maxModels else { return }
    let fm = FileManager.default
    guard let items = try? fm.contentsOfDirectory(atPath: root) else { return }
    for name in items {
      if out.count >= Self.maxModels || visited >= Self.maxEntries { return }
      visited += 1
      let path = (root as NSString).appendingPathComponent(name)
      if isModel(name) {
        out.append(path)
      } else {
        var isDir: ObjCBool = false
        if fm.fileExists(atPath: path, isDirectory: &isDir), isDir.boolValue {
          listModels(path, depth: depth + 1, visited: &visited, into: &out)
        }
      }
    }
  }
}
