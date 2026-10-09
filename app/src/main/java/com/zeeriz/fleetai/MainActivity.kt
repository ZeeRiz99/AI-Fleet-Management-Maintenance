package com.zeeriz.fleetai

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.zeeriz.fleetai.data.local.ThemeMode
import com.zeeriz.fleetai.navigation.FleetApp
import com.zeeriz.fleetai.ui.theme.FleetTheme

class MainActivity : ComponentActivity() {

    /** Keeps the system splash visible until saved settings (theme, session) have been read. */
    @Volatile
    private var settingsReady = false

    override fun onCreate(savedInstanceState: Bundle?) {
        val splash = installSplashScreen()
        super.onCreate(savedInstanceState)
        splash.setKeepOnScreenCondition { !settingsReady }
        enableEdgeToEdge()

        val container = (application as FleetApplication).container
        setContent {
            val settings by container.settings.settings.collectAsStateWithLifecycle(initialValue = null)
            val current = settings
            LaunchedEffect(current) { if (current != null) settingsReady = true }
            if (current != null) {
                val dark = when (current.themeMode) {
                    ThemeMode.LIGHT -> false
                    ThemeMode.DARK -> true
                    ThemeMode.SYSTEM -> isSystemInDarkTheme()
                }
                FleetTheme(darkTheme = dark) {
                    FleetApp(container = container, settings = current)
                }
            }
        }
    }
}
