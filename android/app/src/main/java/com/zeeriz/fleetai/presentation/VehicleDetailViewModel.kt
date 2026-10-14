package com.zeeriz.fleetai.presentation

import androidx.lifecycle.ViewModel
import androidx.lifecycle.createSavedStateHandle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.zeeriz.fleetai.data.local.DataSource
import com.zeeriz.fleetai.data.local.SettingsStore
import com.zeeriz.fleetai.data.remote.ApiResult
import com.zeeriz.fleetai.data.repository.FleetRepository
import com.zeeriz.fleetai.domain.model.ServiceRecordResult
import com.zeeriz.fleetai.domain.model.VehicleDetail
import com.zeeriz.fleetai.navigation.Routes
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** One-off results shown as a dialog/snackbar after an AI action. */
sealed interface VehicleEvent {
    data class ServiceRecorded(val result: ServiceRecordResult) : VehicleEvent
    data class Rescored(val riskPercent: Int) : VehicleEvent
    data class Failed(val message: String) : VehicleEvent
}

class VehicleDetailViewModel(val vehicleId: Int, private val repository: FleetRepository, settings: SettingsStore) : ViewModel() {
    /** Recording a service / re-running the model needs the live server (not the read-only GitHub data). */
    val liveServer: StateFlow<Boolean> = settings.settings.map { it.dataSource == DataSource.SERVER }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), true)

    private val _state = MutableStateFlow(ScreenState<VehicleDetail>())
    val state: StateFlow<ScreenState<VehicleDetail>> = _state.asStateFlow()

    /** True while an AI action (re-run model / record service) is in progress. */
    private val _busy = MutableStateFlow(false)
    val busy: StateFlow<Boolean> = _busy.asStateFlow()

    private val _event = MutableStateFlow<VehicleEvent?>(null)
    val event: StateFlow<VehicleEvent?> = _event.asStateFlow()

    init {
        load()
    }

    fun load(refresh: Boolean = false) {
        _state.update { if (refresh) it.copy(refreshing = true) else it.copy(loading = it.data == null, error = null) }
        viewModelScope.launch { _state.update { it.with(repository.vehicle(vehicleId)) } }
    }

    /** Re-runs the real model on the server (features recomputed from the current database). */
    fun rerunModel() = runAction {
        when (val r = repository.predict(vehicleId)) {
            is ApiResult.Success -> {
                _state.update { it.with(repository.vehicle(vehicleId)) }
                VehicleEvent.Rescored((r.data.riskProbability * 100).toInt())
            }
            is ApiResult.Failure -> VehicleEvent.Failed(r.message)
        }
    }

    /** Records the recommended service as done; the server re-scores and returns before/after risk. */
    fun recordService(service: String) = runAction {
        when (val r = repository.recordService(vehicleId, service)) {
            is ApiResult.Success -> {
                _state.update { it.with(repository.vehicle(vehicleId)) }
                VehicleEvent.ServiceRecorded(r.data)
            }
            is ApiResult.Failure -> VehicleEvent.Failed(r.message)
        }
    }

    fun consumeEvent() {
        _event.value = null
    }

    private fun runAction(block: suspend () -> VehicleEvent) {
        if (_busy.value) return
        _busy.value = true
        viewModelScope.launch {
            _event.value = block()
            _busy.value = false
        }
    }

    companion object {
        val Factory = viewModelFactory {
            initializer {
                val id = checkNotNull(createSavedStateHandle().get<Int>(Routes.VEHICLE_ID)) { "vehicleId missing" }
                VehicleDetailViewModel(id, container.repository, container.settings)
            }
        }
    }
}
