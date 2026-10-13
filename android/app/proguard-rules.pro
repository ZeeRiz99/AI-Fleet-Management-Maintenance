# Release builds are not minified (isMinifyEnabled = false). If minification is enabled later,
# keep the kotlinx.serialization generated serializers:
-keepattributes *Annotation*, InnerClasses
-keepclassmembers class com.zeeriz.fleetai.data.** {
    *** Companion;
    kotlinx.serialization.KSerializer serializer(...);
}
