package com.zeeriz.fleetai.presentation

import androidx.lifecycle.ViewModel
import androidx.lifecycle.createSavedStateHandle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.zeeriz.fleetai.data.remote.ApiResult
import com.zeeriz.fleetai.data.repository.FleetRepository
import com.zeeriz.fleetai.domain.model.DriverDetail
import com.zeeriz.fleetai.domain.model.DriverList
import com.zeeriz.fleetai.domain.model.DriverSummary
import com.zeeriz.fleetai.domain.model.Trip
import com.zeeriz.fleetai.navigation.Routes
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

enum class DriverSort(val label: String) { SAFETY_LOW("Needs attention"), SAFETY_HIGH("Safest"), PERFORMANCE("Performance"), NAME("Name") }

fun List<DriverSummary>.sortDrivers(sort: DriverSort): List<DriverSummary> = when (sort) {
    DriverSort.SAFETY_LOW -> sortedBy { it.safetyScore }
    DriverSort.SAFETY_HIGH -> sortedByDescending { it.safetyScore }
    DriverSort.PERFORMANCE -> sortedByDescending { it.performanceScore }
    DriverSort.NAME -> sortedBy { it.name }
}

class DriversViewModel(private val repository: FleetRepository) : ViewModel() {
    private val _state = MutableStateFlow(ScreenState<DriverList>())
    val state: StateFlow<ScreenState<DriverList>> = _state.asStateFlow()

    private val _sort = MutableStateFlow(DriverSort.SAFETY_LOW)
    val sort: StateFlow<DriverSort> = _sort.asStateFlow()

    init {
        load()
    }

    fun setSort(sort: DriverSort) {
        _sort.value = sort
    }

    fun load(refresh: Boolean = false) {
        _state.update { if (refresh) it.copy(refreshing = true) else it.copy(loading = it.data == null, error = null) }
        viewModelScope.launch { _state.update { it.with(repository.drivers()) } }
    }

    companion object {
        val Factory = viewModelFactory { initializer { DriversViewModel(container.repository) } }
    }
}

class DriverDetailViewModel(private val driverId: Int, private val repository: FleetRepository) : ViewModel() {
    private val _state = MutableStateFlow(ScreenState<DriverDetail>())
    val state: StateFlow<ScreenState<DriverDetail>> = _state.asStateFlow()

    init {
        load()
    }

    fun load(refresh: Boolean = false) {
        _state.update { if (refresh) it.copy(refreshing = true) else it.copy(loading = it.data == null, error = null) }
        viewModelScope.launch { _state.update { it.with(repository.driver(driverId)) } }
    }

    companion object {
        val Factory = viewModelFactory {
            initializer {
                val id = checkNotNull(createSavedStateHandle().get<Int>(Routes.DRIVER_ID)) { "driverId missing" }
                DriverDetailViewModel(id, container.repository)
            }
        }
    }
}

data class TripsState(
    val items: List<Trip> = emptyList(),
    val total: Int = 0,
    val active: Int = 0,
    val note: String = "",
    val loading: Boolean = true,
    val loadingMore: Boolean = false,
    val error: String? = null,
    val offlineSince: Long? = null,
) {
    val canLoadMore: Boolean get() = items.size < total
}

class TripsViewModel(private val repository: FleetRepository) : ViewModel() {
    private val _state = MutableStateFlow(TripsState())
    val state: StateFlow<TripsState> = _state.asStateFlow()

    init {
        load(reset = true)
    }

    fun load(reset: Boolean) {
        val s = _state.value
        if (!reset && (s.loadingMore || !s.canLoadMore)) return
        val offset = if (reset) 0 else s.items.size
        _state.update { if (reset) it.copy(loading = it.items.isEmpty(), error = null) else it.copy(loadingMore = true) }
        viewModelScope.launch {
            when (val r = repository.trips(offset)) {
                is ApiResult.Success -> _state.update {
                    it.copy(
                        items = if (reset) r.data.items else it.items + r.data.items,
                        total = r.data.total, active = r.data.active, note = r.data.note,
                        loading = false, loadingMore = false, error = null,
                        offlineSince = if (r.fromCache) r.savedAt else null,
                    )
                }
                is ApiResult.Failure -> _state.update { it.copy(loading = false, loadingMore = false, error = r.message) }
            }
        }
    }

    companion object {
        val Factory = viewModelFactory { initializer { TripsViewModel(container.repository) } }
    }
}
