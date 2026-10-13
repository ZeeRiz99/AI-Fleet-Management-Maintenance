package com.zeeriz.fleetai.presentation

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.zeeriz.fleetai.data.remote.ApiResult
import com.zeeriz.fleetai.data.repository.FleetRepository
import com.zeeriz.fleetai.domain.model.Dashboard
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * Generic screen state used by every data screen: first load, pull-to-refresh, offline (cached) data and errors.
 */
data class ScreenState<T>(
    val data: T? = null,
    val loading: Boolean = true,
    val refreshing: Boolean = false,
    val error: String? = null,
    val offlineSince: Long? = null,
)

/** Applies an [ApiResult] to a [ScreenState]: keeps old data on failure, notes when data came from the cache. */
fun <T> ScreenState<T>.with(result: ApiResult<T>): ScreenState<T> = when (result) {
    is ApiResult.Success -> copy(
        data = result.data, loading = false, refreshing = false, error = null,
        offlineSince = if (result.fromCache) result.savedAt else null,
    )
    is ApiResult.Failure -> copy(loading = false, refreshing = false, error = result.message)
}

class DashboardViewModel(private val repository: FleetRepository) : ViewModel() {
    private val _state = MutableStateFlow(ScreenState<Dashboard>())
    val state: StateFlow<ScreenState<Dashboard>> = _state.asStateFlow()

    init {
        load()
    }

    fun load(refresh: Boolean = false) {
        _state.update { if (refresh) it.copy(refreshing = true) else it.copy(loading = it.data == null, error = null) }
        viewModelScope.launch {
            val result = repository.dashboard()
            _state.update { it.with(result) }
        }
    }

    companion object {
        val Factory = viewModelFactory {
            initializer { DashboardViewModel(container.repository) }
        }
    }
}
