import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

// Release signing: local.properties (git-ignored) may point to a properties file kept OUTSIDE the repo with
// storeFile / storePassword / keyAlias / keyPassword. Without it the release build is simply unsigned.
val localProps: Properties = Properties().apply {
    rootProject.file("local.properties").takeIf { it.exists() }?.inputStream()?.use(::load)
}
val signingProps: Properties? = localProps.getProperty("fleetai.signing")
    ?.let { file(it) }?.takeIf { it.exists() }
    ?.let { f -> Properties().apply { f.inputStream().use(::load) } }

android {
    namespace = "com.zeeriz.fleetai"
    compileSdk {
        version = release(36) {
            minorApiLevel = 1
        }
    }

    defaultConfig {
        applicationId = "com.zeeriz.fleetai"
        minSdk = 26
        targetSdk = 36
        versionCode = 2
        versionName = "1.1"

        // Default FastAPI address: 10.0.2.2 is the laptop as seen from the Android emulator.
        // A real phone on the same Wi-Fi uses http://<laptop-ip>:8000 (changeable in Profile > Server).
        buildConfigField("String", "DEFAULT_API_URL", "\"http://10.0.2.2:8000\"")
        // Read-only API snapshot published in the repo (api/export_static.py); the default data source
        buildConfigField("String", "STATIC_DATA_URL",
            "\"https://raw.githubusercontent.com/ZeeRiz99/AI-Fleet-Management-Maintenance/main/static-api/v1/\"")
        buildConfigField("String", "DEFAULT_DATA_SOURCE", "\"GITHUB\"")
        buildConfigField("String", "DASHBOARD_URL", "\"https://ai-fleet-management.streamlit.app/\"")
        buildConfigField("String", "REPO_URL", "\"https://github.com/ZeeRiz99/AI-Fleet-Management-Maintenance\"")
        // FleetLog AI chat (ops/web.py on Vercel). From local.properties (git-ignored): fleetlog.url, fleetlog.appKey.
        // The app key is a soft gate that ships inside the APK; server-side limits protect the free AI quotas.
        buildConfigField("String", "ASSISTANT_URL", "\"${localProps.getProperty("fleetlog.url", "")}\"")
        buildConfigField("String", "ASSISTANT_KEY", "\"${localProps.getProperty("fleetlog.appKey", "")}\"")
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    signingConfigs {
        if (signingProps != null) {
            create("release") {
                storeFile = file(signingProps.getProperty("storeFile"))
                storePassword = signingProps.getProperty("storePassword")
                keyAlias = signingProps.getProperty("keyAlias")
                keyPassword = signingProps.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.findByName("release")
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.material.icons.core)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.retrofit)
    implementation(libs.retrofit.kotlinx.serialization)
    implementation(libs.okhttp)
    implementation(libs.okhttp.logging)
    implementation(libs.androidx.datastore.preferences)
    implementation(libs.androidx.core.splashscreen)
    debugImplementation(libs.androidx.compose.ui.tooling)
    testImplementation(libs.junit)
}
