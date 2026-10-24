package com.zeeriz.fleetai.data.local

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.zeeriz.fleetai.BuildConfig
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import java.util.UUID

private val Context.dataStore by preferencesDataStore(name = "fleet_settings")

enum class ThemeMode { SYSTEM, LIGHT, DARK }

/**
 * Where the app reads fleet data from. GITHUB = read-only snapshot of the API published in the repo (works on any
 * phone, no server); SERVER = the live FastAPI backend (needed for writes such as recording a service).
 */
enum class DataSource { GITHUB, SERVER }

data class AppSettings(
    val themeMode: ThemeMode = ThemeMode.SYSTEM,
    val dataSource: DataSource = DEFAULT_DATA_SOURCE,
    val serverUrl: String = BuildConfig.DEFAULT_API_URL,
    val token: String? = null,
    val username: String? = null,
    val fullName: String? = null,
) {
    val isLoggedIn: Boolean get() = !token.isNullOrBlank()

    /** GitHub data needs no account; the live server needs a signed-in user. */
    val canBrowse: Boolean get() = dataSource == DataSource.GITHUB || isLoggedIn
}

private val DEFAULT_DATA_SOURCE = runCatching { DataSource.valueOf(BuildConfig.DEFAULT_DATA_SOURCE) }.getOrDefault(DataSource.GITHUB)

/** User preferences and the login session, persisted with DataStore (no secrets are hard-coded in the app). */
class SettingsStore(private val context: Context) {

    val settings: Flow<AppSettings> = context.dataStore.data.map { p ->
        AppSettings(
            themeMode = p[THEME]?.let { runCatching { ThemeMode.valueOf(it) }.getOrNull() } ?: ThemeMode.SYSTEM,
            dataSource = p[DATA_SOURCE]?.let { runCatching { DataSource.valueOf(it) }.getOrNull() } ?: DEFAULT_DATA_SOURCE,
            serverUrl = p[SERVER_URL] ?: BuildConfig.DEFAULT_API_URL,
            token = p[TOKEN],
            username = p[USERNAME],
            fullName = p[FULL_NAME],
        )
    }

    suspend fun setThemeMode(mode: ThemeMode) {
        context.dataStore.edit { it[THEME] = mode.name }
    }

    suspend fun setDataSource(source: DataSource) {
        context.dataStore.edit { it[DATA_SOURCE] = source.name }
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

    /** Random id for the FleetLog AI chat (created on first use, kept until the user starts over). */
    suspend fun assistantSession(): String {
        var id: String? = null
        context.dataStore.edit { p ->
            id = p[ASSISTANT_SESSION] ?: UUID.randomUUID().toString().also { p[ASSISTANT_SESSION] = it }
        }
        return checkNotNull(id)
    }

    suspend fun resetAssistantSession() {
        context.dataStore.edit { it.remove(ASSISTANT_SESSION) }
    }

    private companion object {
        val ASSISTANT_SESSION = stringPreferencesKey("assistant_session")
        val THEME = stringPreferencesKey("theme_mode")
        val DATA_SOURCE = stringPreferencesKey("data_source")
        val SERVER_URL = stringPreferencesKey("server_url")
        val TOKEN = stringPreferencesKey("token")
        val USERNAME = stringPreferencesKey("username")
        val FULL_NAME = stringPreferencesKey("full_name")
    }
}
