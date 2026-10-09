// Top-level build file. AGP 9 ships built-in Kotlin support, so no separate kotlin-android plugin is applied.
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.compose) apply false
    alias(libs.plugins.kotlin.serialization) apply false
}
