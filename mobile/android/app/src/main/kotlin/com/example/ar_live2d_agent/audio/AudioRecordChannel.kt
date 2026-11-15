package com.example.ar_live2d_agent.audio

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Handler
import android.os.Looper
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodChannel

/**
 * 16kHz / mono / PCM16，160ms 一块（6400B）经 EventChannel 流式回传 Dart。
 * 采集逻辑只在平台适配层；MainActivity 仅注册，不写业务。
 */
class AudioRecordChannel private constructor(
    private val context: Context,
    messenger: BinaryMessenger,
) {
    companion object {
        private const val METHOD_CHANNEL = "ar_live2d_agent/audio"
        private const val EVENT_CHANNEL = "ar_live2d_agent/audio_stream"
        private const val SAMPLE_RATE = 16000
        private const val CHUNK_BYTES = 6400

        @Volatile
        private var instance: AudioRecordChannel? = null

        fun register(messenger: BinaryMessenger, context: Context) {
            instance = AudioRecordChannel(context, messenger)
        }
    }

    private val mainHandler = Handler(Looper.getMainLooper())
    private var sink: EventChannel.EventSink? = null
    private var recorder: AudioRecord? = null
    private var worker: Thread? = null

    @Volatile
    private var running = false

    init {
        MethodChannel(messenger, METHOD_CHANNEL).setMethodCallHandler { call, result ->
            when (call.method) {
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
        EventChannel(messenger, EVENT_CHANNEL).setStreamHandler(
            object : EventChannel.StreamHandler {
                override fun onListen(arguments: Any?, events: EventChannel.EventSink?) {
                    sink = events
                }

                override fun onCancel(arguments: Any?) {
                    sink = null
                }
            }
        )
    }

    @SuppressLint("MissingPermission")
    private fun start() {
        if (running) return
        if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            mainHandler.post {
                sink?.error("PERMISSION", "RECORD_AUDIO not granted", null)
            }
            return
        }
        val minBuf = AudioRecord.getMinBufferSize(
            SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT
        )
        val bufSize = maxOf(minBuf, CHUNK_BYTES)
        val rec = AudioRecord(
            MediaRecorder.AudioSource.VOICE_RECOGNITION,
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            bufSize,
        )
        if (rec.state != AudioRecord.STATE_INITIALIZED) {
            rec.release()
            return
        }
        recorder = rec
        rec.startRecording()
        running = true
        worker = Thread {
            val buf = ByteArray(CHUNK_BYTES)
            var carry = ByteArray(0)
            while (running) {
                val read = rec.read(buf, 0, buf.size)
                if (read <= 0) continue
                val merged = carry + buf.copyOf(read)
                var offset = 0
                while (offset + CHUNK_BYTES <= merged.size) {
                    val chunk = merged.copyOfRange(offset, offset + CHUNK_BYTES)
                    mainHandler.post { sink?.success(chunk) }
                    offset += CHUNK_BYTES
                }
                carry = merged.copyOfRange(offset, merged.size)
            }
            if (carry.isNotEmpty()) mainHandler.post { sink?.success(carry) }
        }.apply {
            name = "AudioRecordChannel"
            start()
        }
    }

    private fun stop() {
        running = false
        worker?.join(300)
        worker = null
        try {
            recorder?.stop()
        } catch (_: Exception) {
        }
        recorder?.release()
        recorder = null
    }
}
