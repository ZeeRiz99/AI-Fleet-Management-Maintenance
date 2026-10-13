package com.zeeriz.fleetai.presentation

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.zeeriz.fleetai.data.local.SettingsStore
import com.zeeriz.fleetai.data.remote.ApiResult
import com.zeeriz.fleetai.data.repository.FleetRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class LoginUiState(
    val username: String = "",
    val password: String = "",
    val serverUrl: String = "",
    val loading: Boolean = false,
    val error: String? = null,
) {
    val canSubmit: Boolean get() = username.isNotBlank() && password.isNotBlank() && serverUrl.isNotBlank() && !loading
}

class LoginViewModel(private val repository: FleetRepository, settings: SettingsStore) : ViewModel() {
    private val _state = MutableStateFlow(LoginUiState())
    val state: StateFlow<LoginUiState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            val saved = settings.settings.first()
            _state.update { it.copy(serverUrl = saved.serverUrl, username = saved.username.orEmpty()) }
        }
    }

    fun onUsername(value: String) = _state.update { it.copy(username = value, error = null) }
    fun onPassword(value: String) = _state.update { it.copy(password = value, error = null) }
    fun onServerUrl(value: String) = _state.update { it.copy(serverUrl = value, error = null) }

    /** On success the saved session changes and the navigation graph moves to the dashboard. */
    fun signIn() {
        val s = _state.value
        if (!s.canSubmit) return
        _state.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            when (val result = repository.login(s.username, s.password, s.serverUrl)) {
                is ApiResult.Success -> _state.update { it.copy(loading = false, password = "") }
                is ApiResult.Failure -> _state.update { it.copy(loading = false, error = result.message) }
            }
        }
    }

    companion object {
        val Factory = viewModelFactory {
            initializer { LoginViewModel(container.repository, container.settings) }
        }
    }
}
