package com.example.ar_live2d_agent.audio

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.MethodChannel

/**
 * 系统内置语音识别：无电脑端 / 离线时由 Dart 侧 AsrMode.auto 自动回退到这里。
 * 不新增任何 Gradle 依赖；识别文本通过 MethodChannel 反向回调 `onText`。
 * 中间结果用 `onText` 推送 partial，最终结果用 `onText` 推送最终串（Dart 侧覆盖台词）。
 */
class SystemAsrChannel private constructor(
    private val context: Context,
    messenger: BinaryMessenger,
) {
    companion object {
        private const val CHANNEL = "ar_live2d_agent/system_asr"

        @Volatile
        private var instance: SystemAsrChannel? = null

        fun register(messenger: BinaryMessenger, context: Context) {
            instance = SystemAsrChannel(context.applicationContext, messenger)
        }
    }

    private val channel = MethodChannel(messenger, CHANNEL)
    private val main = Handler(Looper.getMainLooper())
    private var recognizer: SpeechRecognizer? = null
    @Volatile
    private var lastText = ""

    init {
        channel.setMethodCallHandler { call, result ->
            when (call.method) {
                "available" -> result.success(SpeechRecognizer.isRecognitionAvailable(context))
                "start" -> {
                    start()
                    result.success(null)
                }
                "stop" -> {
                    stop()
                    result.success(null)
                }
                else -> result.notImplemented()
            }
        }
    }

    private fun start() {
        main.post {
            if (!SpeechRecognizer.isRecognitionAvailable(context)) {
                emitError("系统识别服务不可用")
                return@post
            }
            stopInternal()
            lastText = ""
            val r = SpeechRecognizer.createSpeechRecognizer(context)
            recognizer = r
            r.setRecognitionListener(object : RecognitionListener {
                override fun onReadyForSpeech(params: Bundle?) {}
                override fun onBeginningOfSpeech() {}
                override fun onRmsChanged(rmsdB: Float) {}
                override fun onBufferReceived(buffer: ByteArray?) {}
                override fun onEndOfSpeech() {}
                override fun onError(error: Int) {
                    emitError("系统识别失败（$error），请重试")
                }
                override fun onResults(results: Bundle?) {
                    val list = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    emitText(list?.firstOrNull().orEmpty())
                }
                override fun onPartialResults(partialResults: Bundle?) {
                    val list = partialResults
                        ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    emitText(list?.firstOrNull().orEmpty())
                }
                override fun onEvent(eventType: Int, params: Bundle?) {}
            })
            val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                    RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
                putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
            }
            try {
                r.startListening(intent)
            } catch (e: Exception) {
                emitError("启动失败：${e.javaClass.simpleName}")
            }
        }
    }

    private fun stop() {
        main.post { stopInternal() }
    }

    private fun stopInternal() {
        try {
            recognizer?.stopListening()
        } catch (_: Exception) {
        }
        try {
            recognizer?.destroy()
        } catch (_: Exception) {
        }
        recognizer = null
    }

    private fun emitText(text: String) {
        val t = text.trim()
        if (t.isEmpty() || t == lastText) return
        lastText = t
        main.post {
            channel.invokeMethod("onText", mapOf("text" to t))
        }
    }

    private fun emitError(message: String) {
        main.post {
            channel.invokeMethod("onError", mapOf("message" to message))
        }
    }
}
