package com.example.ar_live2d_agent.picker

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Environment
import android.provider.DocumentsContract
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.MethodChannel

/**
 * 系统底层目录选择器（SAF ACTION_OPEN_DOCUMENT_TREE）。
 *
 * 只做「关联」：拿 tree URI、申请持久读权限、尽力解析成可枚举的真实路径，
 * 并用 DocumentsContract 列出模型文件；**不复制、不移动、不导入任何模型文件**。
 * 非 primary 存储无法解析文件路径时返回 content:// 引用 + 明确提示。
 */
class DirectoryPickerChannel private constructor(
    private val activity: Activity,
    messenger: BinaryMessenger,
) {
    companion object {
        private const val CHANNEL = "ar_live2d_agent/directory_picker"
        private const val REQ = 0x4C44
        private const val MAX_MODELS = 64
        private const val MAX_DEPTH = 2
        private val MODEL_EXT = listOf(".model3.json", ".model.json", ".moc3")

        @Volatile
        private var instance: DirectoryPickerChannel? = null

        fun register(messenger: BinaryMessenger, activity: Activity) {
            instance = DirectoryPickerChannel(activity, messenger)
        }

        /** 由 MainActivity.onActivityResult 转发；返回 true 表示已消费。 */
        fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?): Boolean =
            instance?.handleResult(requestCode, resultCode, data) ?: false
    }

    private val channel = MethodChannel(messenger, CHANNEL)
    private var pending: MethodChannel.Result? = null

    init {
        channel.setMethodCallHandler { call, result ->
            when (call.method) {
                "pick" -> {
                    if (pending != null) {
                        result.success(null)
                    } else {
                        pending = result
                        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).apply {
                            addFlags(
                                Intent.FLAG_GRANT_READ_URI_PERMISSION or
                                    Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION
                            )
                            putExtra(Intent.EXTRA_LOCAL_ONLY, true)
                        }
                        try {
                            activity.startActivityForResult(intent, REQ)
                        } catch (e: Exception) {
                            pending = null
                            result.error("PICK", e.javaClass.simpleName, null)
                        }
                    }
                }
                else -> result.notImplemented()
            }
        }
    }

    private fun handleResult(requestCode: Int, resultCode: Int, data: Intent?): Boolean {
        if (requestCode != REQ) return false
        val result = pending ?: return true
        pending = null
        val uri: Uri? = data?.data
        if (resultCode != Activity.RESULT_OK || uri == null) {
            result.success(null) // 用户取消
            return true
        }
        try {
            activity.contentResolver.takePersistableUriPermission(
                uri, Intent.FLAG_GRANT_READ_URI_PERMISSION
            )
        } catch (_: Exception) {
        }

        val treeId = try {
            DocumentsContract.getTreeDocumentId(uri)
        } catch (_: Exception) {
            uri.lastPathSegment.orEmpty()
        }
        val path = resolvePath(treeId)
        val files = listModels(uri, treeId, path)
        val note = if (path.isEmpty()) {
            "该目录无法解析为文件路径，已返回 content:// 引用；"
            "请优先选择内部存储目录，或手动粘贴绝对路径"
        } else {
            ""
        }
        result.success(
            mapOf(
                "path" to path,
                "uri" to uri.toString(),
                "display" to (uri.lastPathSegment ?: treeId),
                "files" to files,
                "note" to note,
            )
        )
        return true
    }

    /** primary:Live2D/x -> /storage/emulated/0/Live2D/x；其它卷尽力推断。 */
    private fun resolvePath(treeId: String): String {
        val colon = treeId.indexOf(':')
        if (treeId.startsWith("raw:") && colon >= 0) {
            return treeId.substring(colon + 1)
        }
        if (colon < 0) return ""
        val volume = treeId.substring(0, colon)
        val rel = treeId.substring(colon + 1)
        val base = if (volume == "primary") {
            Environment.getExternalStorageDirectory().absolutePath
        } else {
            "/storage/$volume"
        }
        val candidate = if (rel.isEmpty()) base else "$base/$rel"
        return if (java.io.File(candidate).isDirectory) candidate else ""
    }

    private fun isModel(name: String): Boolean {
        val lower = name.lowercase()
        return MODEL_EXT.any { lower.endsWith(it) }
    }

    private fun listModels(treeUri: Uri, rootDocId: String, rootPath: String): List<String> {
        val out = mutableListOf<String>()
        try {
            walk(treeUri, rootDocId, 0, rootPath, out)
        } catch (_: Exception) {
        }
        return out
    }

    private fun walk(
        treeUri: Uri,
        docId: String,
        depth: Int,
        currentPath: String,
        out: MutableList<String>,
    ) {
        if (depth > MAX_DEPTH || out.size >= MAX_MODELS) return
        val childrenUri = DocumentsContract.buildChildDocumentsUriUsingTree(treeUri, docId)
        val projection = arrayOf(
            DocumentsContract.Document.COLUMN_DOCUMENT_ID,
            DocumentsContract.Document.COLUMN_DISPLAY_NAME,
            DocumentsContract.Document.COLUMN_MIME_TYPE,
        )
        val cursor = try {
            activity.contentResolver.query(childrenUri, projection, null, null, null)
        } catch (_: Exception) {
            null
        } ?: return
        cursor.use { c ->
            val idIdx = c.getColumnIndex(DocumentsContract.Document.COLUMN_DOCUMENT_ID)
            val nameIdx = c.getColumnIndex(DocumentsContract.Document.COLUMN_DISPLAY_NAME)
            val mimeIdx = c.getColumnIndex(DocumentsContract.Document.COLUMN_MIME_TYPE)
            while (c.moveToNext() && out.size < MAX_MODELS) {
                val id = if (idIdx >= 0) c.getString(idIdx) ?: continue else continue
                val name = if (nameIdx >= 0) c.getString(nameIdx) ?: continue else continue
                val mime = if (mimeIdx >= 0) c.getString(mimeIdx) ?: "" else ""
                if (isModel(name)) {
                    out.add(
                        if (currentPath.isNotEmpty()) "$currentPath/$name"
                        else "$treeUri/$name"
                    )
                } else if (mime == DocumentsContract.Document.MIME_TYPE_DIR) {
                    walk(
                        treeUri,
                        id,
                        depth + 1,
                        if (currentPath.isNotEmpty()) "$currentPath/$name" else "",
                        out,
                    )
                }
            }
        }
    }
}
