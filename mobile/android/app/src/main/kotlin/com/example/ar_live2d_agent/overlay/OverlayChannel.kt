package com.example.ar_live2d_agent.overlay

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.provider.Settings
import android.util.TypedValue
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.TextView
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.MethodChannel

/**
 * 「Live2D 模型在所有应用之上置顶」Android 悬浮窗。
 *
 * 需要 SYSTEM_ALERT_WINDOW 权限（Dart 侧用 permission_handler 引导授权）。
 * 当前视图是可拖动的角色名牌 + 状态条：真正的 Live2D 纹理需要把原生 Cubism
 * 渲染或 Flutter 引擎 texture 挂进这个 Window，这一步留给接入模型 SDK 时补齐；
 * Dart 侧在浮窗开启期间仍以低帧率驱动舞台状态，并把模型缩小在右侧探头。
 *
 * 色系（blue / night / cream）与缩放比例由 Dart 侧传入，可运行时更新而不重建窗口。
 */
class OverlayChannel private constructor(
    private val context: Context,
    messenger: BinaryMessenger,
) {
    companion object {
        private const val CHANNEL = "ar_live2d_agent/overlay"
        private const val BASE_SCALE = 0.55f

        @Volatile
        private var instance: OverlayChannel? = null

        fun register(messenger: BinaryMessenger, context: Context) {
            instance = OverlayChannel(context.applicationContext, messenger)
        }
    }

    private val channel = MethodChannel(messenger, CHANNEL)
    private val wm = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
    private var floating: View? = null
    private var label: TextView? = null

    private var currentName = "她"
    private var currentScheme = "blue"
    private var currentScale = BASE_SCALE

    init {
        channel.setMethodCallHandler { call, result ->
            when (call.method) {
                "available" -> result.success(true)
                "canDraw" -> result.success(canDraw())
                "start" -> {
                    currentName = call.argument<String>("name") ?: currentName
                    currentScheme = call.argument<String>("scheme") ?: currentScheme
                    currentScale = (call.argument<Any>("scale") as? Number)
                        ?.toFloat() ?: BASE_SCALE
                    result.success(start())
                }
                "updateAppearance" -> {
                    call.argument<String>("name")?.let { currentName = it }
                    call.argument<String>("scheme")?.let { currentScheme = it }
                    (call.argument<Any>("scale") as? Number)?.toFloat()
                        ?.let { currentScale = it }
                    applyAppearance()
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

    private fun canDraw(): Boolean =
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) true
        else Settings.canDrawOverlays(context)

    private data class Look(val bg: Int, val border: Int, val text: Int)

    private fun look(): Look = when (currentScheme) {
        "night" -> Look(0xE608080C.toInt(), 0xFF3B3C48.toInt(), 0xFFB9C6D6.toInt())
        "cream" -> Look(0xE6FFFBF4.toInt(), 0xFFD8C3A5.toInt(), 0xFF3E6E9E.toInt())
        else -> Look(0xE60A1B36.toInt(), 0xFF2C5A8C.toInt(), 0xFF7FD4FF.toInt())
    }

    @SuppressLint("InflateParams", "ClickableViewAccessibility")
    private fun start(): Boolean {
        if (!canDraw()) return false
        if (floating != null) {
            applyAppearance()
            return true
        }
        val l = look()
        val root = FrameLayout(context)
        val bg = GradientDrawable().apply {
            setColor(l.bg)
            cornerRadius = 24f
            setStroke(2, l.border)
        }
        root.background = bg
        root.elevation = 12f

        val tv = TextView(context).apply {
            setTextColor(l.text)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
            typeface = Typeface.DEFAULT_BOLD
            setPadding(28, 18, 28, 18)
            gravity = Gravity.CENTER
        }
        root.addView(tv)
        label = tv

        val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        else
            @Suppress("DEPRECATION")
            WindowManager.LayoutParams.TYPE_PHONE

        val lp = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            type,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL or
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            android.graphics.PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.TOP or Gravity.END
            x = 24
            y = 120
        }

        var downX = 0
        var downY = 0
        var originX = 0
        var originY = 0
        root.setOnTouchListener { v, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    downX = event.rawX.toInt()
                    downY = event.rawY.toInt()
                    originX = lp.x
                    originY = lp.y
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    lp.x = originX - (event.rawX.toInt() - downX)
                    lp.y = originY + (event.rawY.toInt() - downY)
                    try {
                        wm.updateViewLayout(v, lp)
                    } catch (_: Exception) {
                    }
                    true
                }
                else -> false
            }
        }

        return try {
            wm.addView(root, lp)
            floating = root
            applyAppearance()
            true
        } catch (_: Exception) {
            false
        }
    }

    private fun applyAppearance() {
        val root = floating ?: return
        val tv = label ?: return
        val l = look()
        val drawable = root.background as? GradientDrawable
        drawable?.setColor(l.bg)
        drawable?.setStroke(2, l.border)
        tv.setTextColor(l.text)
        tv.text = "$currentName · Live2D 置顶中"
        val factor = (currentScale / BASE_SCALE).coerceIn(0.6f, 1.6f)
        root.scaleX = factor
        root.scaleY = factor
        try {
            wm.updateViewLayout(root, root.layoutParams)
        } catch (_: Exception) {
        }
    }

    private fun stop() {
        val v = floating ?: return
        try {
            wm.removeView(v)
        } catch (_: Exception) {
        }
        floating = null
        label = null
    }
}
