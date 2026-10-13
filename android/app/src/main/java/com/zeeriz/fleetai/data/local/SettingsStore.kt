package com.zeeriz.fleetai.data.local

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.zeeriz.fleetai.BuildConfig
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = "fleet_settings")

enum class ThemeMode { SYSTEM, LIGHT, DARK }

data class AppSettings(
    val themeMode: ThemeMode = ThemeMode.SYSTEM,
    val serverUrl: String = BuildConfig.DEFAULT_API_URL,
    val token: String? = null,
    val username: String? = null,
    val fullName: String? = null,
) {
    val isLoggedIn: Boolean get() = !token.isNullOrBlank()
}

/** User preferences and the login session, persisted with DataStore (no secrets are hard-coded in the app). */
class SettingsStore(private val context: Context) {

    val settings: Flow<AppSettings> = context.dataStore.data.map { p ->
        AppSettings(
            themeMode = p[THEME]?.let { runCatching { ThemeMode.valueOf(it) }.getOrNull() } ?: ThemeMode.SYSTEM,
            serverUrl = p[SERVER_URL] ?: BuildConfig.DEFAULT_API_URL,
            token = p[TOKEN],
            username = p[USERNAME],
            fullName = p[FULL_NAME],
        )
    }

    suspend fun setThemeMode(mode: ThemeMode) {
        context.dataStore.edit { it[THEME] = mode.name }
    }

    suspend fun setServerUrl(url: String) {
        context.dataStore.edit { it[SERVER_URL] = url.trim().trimEnd('/') }
    }

    suspend fun saveSession(token: String, username: String, fullName: String?) {
        context.dataStore.edit {
            it[TOKEN] = token
            it[USERNAME] = username
            if (fullName != null) it[FULL_NAME] = fullName else it.remove(FULL_NAME)
        }
    }

    suspend fun clearSession() {
        context.dataStore.edit {
            it.remove(TOKEN)
            it.remove(FULL_NAME)
        }
    }

    private companion object {
        val THEME = stringPreferencesKey("theme_mode")
        val SERVER_URL = stringPreferencesKey("server_url")
        val TOKEN = stringPreferencesKey("token")
        val USERNAME = stringPreferencesKey("username")
        val FULL_NAME = stringPreferencesKey("full_name")
    }
}
