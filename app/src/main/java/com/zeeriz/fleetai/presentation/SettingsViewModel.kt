package com.zeeriz.fleetai.presentation

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.zeeriz.fleetai.data.local.AppSettings
import com.zeeriz.fleetai.data.local.SettingsStore
import com.zeeriz.fleetai.data.local.ThemeMode
import com.zeeriz.fleetai.data.repository.FleetRepository
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

/** Profile / Settings: theme, server address, sign-out. */
class SettingsViewModel(private val store: SettingsStore, private val repository: FleetRepository) : ViewModel() {

    val settings: StateFlow<AppSettings> =
        store.settings.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), AppSettings())

    fun setThemeMode(mode: ThemeMode) {
        viewModelScope.launch { store.setThemeMode(mode) }
    }

    fun setServerUrl(url: String) {
        viewModelScope.launch { store.setServerUrl(url) }
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
