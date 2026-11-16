# ============================================================
# Flutter 引擎
# ============================================================
-keep class io.flutter.** { *; }
-keep class io.flutter.plugins.** { *; }
-dontwarn io.flutter.**

# ============================================================
# Flutter 插件（按你项目实际使用的插件补充）
# ============================================================

# camera / camera_android_camerax
-keep class androidx.camera.** { *; }
-dontwarn androidx.camera.**

# mobile_scanner（基于 MLKit / ZXing）
-keep class com.google.mlkit.** { *; }
-keep class com.google.android.gms.** { *; }
-dontwarn com.google.mlkit.**
-dontwarn com.google.android.gms.**

# permission_handler
-keep class com.baseflow.permissionhandler.** { *; }

# shared_preferences
-keep class io.flutter.plugins.sharedpreferences.** { *; }

# flutter_rotation_sensor / native_device_orientation
-keep class dev.fluttercommunity.plus.** { *; }

# flutter_live2d（JNI + native 方法）
-keep class com.example.flutter_live2d.** { *; }
-keepclasseswithmembernames class * {
    native <methods>;
}

# ============================================================
# 通用：反射 / 序列化 / JNI
# ============================================================
# 保留注解
-keepattributes *Annotation*
# 保留泛型、内部类、异常信息（反射常用）
-keepattributes Signature
-keepattributes InnerClasses
-keepattributes EnclosingMethod
-keepattributes SourceFile,LineNumberTable

# 保留所有 native 方法名（JNI 靠名字查找）
-keepclasseswithmembernames class * {
    native <methods>;
}

# 保留枚举的 values() / valueOf()
-keepclassmembers enum * {
    public static **[] values();
    public static ** valueOf(java.lang.String);
}

# 保留 Parcelable
-keep class * implements android.os.Parcelable {
    public static final android.os.Parcelable$Creator *;
}

# 保留 Serializable
-keepclassmembers class * implements java.io.Serializable {
    static final long serialVersionUID;
    private static final java.io.ObjectStreamField[] serialPersistentFields;
    !static !transient <fields>;
    private void writeObject(java.io.ObjectOutputStream);
    private void readObject(java.io.ObjectInputStream);
    java.lang.Object writeReplace();
    java.lang.Object readResolve();
}

# 保留 Pydantic/JSON 模型类（如果有通过反射反序列化的 DTO）
# -keep class com.example.ar_live2d_agent.models.** { *; }