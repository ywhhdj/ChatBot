package com.example.ar_live2d_agent

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import com.example.ar_live2d_agent.audio.AudioRecordChannel

class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        AudioRecordChannel.register(
            flutterEngine.dartExecutor.binaryMessenger,
            applicationContext,
        )
    }
}
