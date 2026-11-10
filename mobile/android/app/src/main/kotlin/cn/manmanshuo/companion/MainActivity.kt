package cn.manmanshuo.companion

import android.app.Activity
import android.content.Intent
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/** Android's document picker saves exports without broad storage permission. */
class MainActivity : FlutterActivity() {
    private var pendingResult: MethodChannel.Result? = null
    private var pendingContent: String? = null
    private val exportRequest = 4201

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "companion/export")
            .setMethodCallHandler { call, result ->
                if (call.method != "saveJson") {
                    result.notImplemented()
                } else if (pendingResult != null) {
                    result.error("EXPORT_ACTIVE", "已有文件正在保存。", null)
                } else {
                    val content = call.argument<String>("content")
                    if (content == null) {
                        result.error("INVALID_DATA", "缺少导出内容。", null)
                    } else {
                        pendingResult = result
                        pendingContent = content
                        try {
                            startActivityForResult(Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
                                addCategory(Intent.CATEGORY_OPENABLE)
                                type = "application/json"
                                putExtra(Intent.EXTRA_TITLE, call.argument<String>("filename") ?: "companion.json")
                            }, exportRequest)
                        } catch (error: Exception) {
                            finishExport(error.message)
                        }
                    }
                }
            }
    }

    @Deprecated("FlutterActivity still forwards this callback for document providers")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != exportRequest) return
        if (resultCode != Activity.RESULT_OK || data?.data == null) {
            pendingResult?.success(false)
            pendingResult = null
            pendingContent = null
            return
        }
        try {
            val stream = contentResolver.openOutputStream(data.data!!, "wt")
                ?: throw IllegalStateException("无法打开所选位置。")
            stream.use { it.write((pendingContent ?: "").toByteArray(Charsets.UTF_8)) }
            pendingResult?.success(true)
            pendingResult = null
            pendingContent = null
        } catch (error: Exception) {
            finishExport(error.message)
        }
    }

    private fun finishExport(message: String?) {
        pendingResult?.error("EXPORT_FAILED", message ?: "保存未完成。", null)
        pendingResult = null
        pendingContent = null
    }
}
