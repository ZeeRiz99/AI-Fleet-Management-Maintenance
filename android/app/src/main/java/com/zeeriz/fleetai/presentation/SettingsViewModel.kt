package com.zeeriz.fleetai.presentation

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.zeeriz.fleetai.data.local.AppSettings
import com.zeeriz.fleetai.data.local.DataSource
import com.zeeriz.fleetai.data.local.SettingsStore
import com.zeeriz.fleetai.data.local.ThemeMode
import com.zeeriz.fleetai.data.remote.ApiResult
import com.zeeriz.fleetai.data.repository.FleetRepository
import com.zeeriz.fleetai.domain.model.ModelInfo
import com.zeeriz.fleetai.utils.Format
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Result of "Test connection" in Profile > Server. */
data class ConnectionStatus(val checking: Boolean = false, val ok: Boolean? = null, val text: String? = null)

/** Profile / Settings: account, theme, data source, server address + connection test, AI model info, reset, sign-out. */
class SettingsViewModel(private val store: SettingsStore, private val repository: FleetRepository) : ViewModel() {

    val settings: StateFlow<AppSettings> =
        store.settings.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), AppSettings())

    private val _connection = MutableStateFlow(ConnectionStatus())
    val connection: StateFlow<ConnectionStatus> = _connection.asStateFlow()

    private val _model = MutableStateFlow(ScreenState<ModelInfo>())
    val model: StateFlow<ScreenState<ModelInfo>> = _model.asStateFlow()

    private val _message = MutableStateFlow<String?>(null)
    val message: StateFlow<String?> = _message.asStateFlow()

    private val _resetting = MutableStateFlow(false)
    val resetting: StateFlow<Boolean> = _resetting.asStateFlow()

    init {
        loadModel()
    }

    fun loadModel() {
        _model.update { it.copy(loading = it.data == null, error = null) }
        viewModelScope.launch { _model.update { it.with(repository.modelInfo()) } }
    }

    fun setThemeMode(mode: ThemeMode) {
        viewModelScope.launch { store.setThemeMode(mode) }
    }

    /** GitHub snapshot <-> live server. Choosing the live server without a session shows the sign-in screen. */
    fun setDataSource(source: DataSource) {
        viewModelScope.launch {
            repository.setDataSource(source)
            _connection.value = ConnectionStatus()
            loadModel()
        }
    }

    fun setServerUrl(url: String) {
        viewModelScope.launch {
            store.setServerUrl(url)
            _connection.value = ConnectionStatus()
        }
    }

    fun testConnection() {
        _connection.value = ConnectionStatus(checking = true)
        viewModelScope.launch {
            val fromGitHub = settings.value.dataSource == DataSource.GITHUB
            _connection.value = when (val r = repository.health()) {
                is ApiResult.Success -> ConnectionStatus(
                    ok = r.data.status == "ok",
                    text = (if (fromGitHub) "GitHub data reachable" else "Connected · API ${r.data.version}") +
                        " · ${r.data.vehicles} vehicles · data as of ${Format.date(r.data.asOf)}",
                )
                is ApiResult.Failure -> ConnectionStatus(ok = false, text = r.message)
            }
        }
    }

    fun resetDemo() {
        _resetting.value = true
        viewModelScope.launch {
            _message.value = when (val r = repository.resetDemo()) {
                is ApiResult.Success -> if (settings.value.dataSource == DataSource.GITHUB) "Changes on this phone cleared. Pull down on other screens to refresh."
                else "Demo data restored (${r.data.vehicles} vehicles re-scored). Pull down on other screens to refresh."
                is ApiResult.Failure -> r.message
            }
            _resetting.value = false
        }
    }

    fun consumeMessage() {
        _message.value = null
    }

    fun signOut() {
        viewModelScope.launch { repository.logout() }
    }

    companion object {
        val Factory = viewModelFactory {
            initializer { SettingsViewModel(container.settings, container.repository) }
        }
    }
}
