package com.example.ar_live2d_agent

import android.content.Intent
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import com.example.ar_live2d_agent.audio.AudioRecordChannel
import com.example.ar_live2d_agent.audio.SystemAsrChannel
import com.example.ar_live2d_agent.overlay.OverlayChannel
import com.example.ar_live2d_agent.picker.DirectoryPickerChannel

class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        val messenger = flutterEngine.dartExecutor.binaryMessenger
        AudioRecordChannel.register(messenger, applicationContext)
        SystemAsrChannel.register(messenger, applicationContext)
        OverlayChannel.register(messenger, applicationContext)
        DirectoryPickerChannel.register(messenger, this)
    }

    @Suppress("DEPRECATION")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        if (!DirectoryPickerChannel.onActivityResult(requestCode, resultCode, data)) {
            super.onActivityResult(requestCode, resultCode, data)
        }
    }
}
