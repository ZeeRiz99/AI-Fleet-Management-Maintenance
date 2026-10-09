package com.zeeriz.fleetai.di

import android.content.Context
import com.zeeriz.fleetai.data.local.SettingsStore

/**
 * Manual dependency container (one instance per app). Keeps wiring explicit without a DI framework;
 * repositories and the network layer are added here as the app grows.
 */
class AppContainer(context: Context) {
    val settings = SettingsStore(context.applicationContext)
}
