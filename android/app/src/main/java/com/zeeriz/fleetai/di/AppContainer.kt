package com.zeeriz.fleetai.di

import android.content.Context
import com.zeeriz.fleetai.BuildConfig
import com.zeeriz.fleetai.data.local.LocalAlertReads
import com.zeeriz.fleetai.data.local.ResponseCache
import com.zeeriz.fleetai.data.local.SettingsStore
import com.zeeriz.fleetai.data.remote.ApiProvider
import com.zeeriz.fleetai.data.remote.GitHubFleetApi
import com.zeeriz.fleetai.data.repository.AssistantRepository
import com.zeeriz.fleetai.data.repository.FleetRepository
import com.zeeriz.fleetai.data.repository.Session
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

/**
 * Manual dependency container (one instance per app). Keeps wiring explicit without a DI framework.
 */
class AppContainer(context: Context) {
    private val appContext = context.applicationContext
    private val appScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private val session = Session()

    val settings = SettingsStore(appContext)
    val repository = FleetRepository(
        settings = settings,
        apiProvider = ApiProvider(tokenProvider = { session.snapshot.token }),
        gitHub = GitHubFleetApi.create(BuildConfig.STATIC_DATA_URL, LocalAlertReads(appContext)),
        cache = ResponseCache(appContext),
        session = session,
    )
    val assistant = AssistantRepository(settings, BuildConfig.ASSISTANT_URL, BuildConfig.ASSISTANT_KEY)

    init {
        // Keep the session snapshot in sync with saved settings (e.g. server address changed in Profile).
        appScope.launch { settings.settings.collect { session.snapshot = it } }
    }
}
