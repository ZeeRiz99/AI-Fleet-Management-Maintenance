package com.zeeriz.fleetai

import android.app.Application
import com.zeeriz.fleetai.di.AppContainer

class FleetApplication : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
    }
}
