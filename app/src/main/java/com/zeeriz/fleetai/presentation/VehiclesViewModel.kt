package com.zeeriz.fleetai.presentation

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.zeeriz.fleetai.data.repository.FleetRepository
import com.zeeriz.fleetai.domain.model.VehicleSummary
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

enum class VehicleSort(val label: String) { RISK("Highest risk"), HEALTH("Lowest health"), REGISTRATION("Registration"), ODOMETER("Mileage") }

data class VehicleFilters(
    val query: String = "",
    val tier: String? = null,       // High / Medium / Low
    val status: String? = null,     // active / maintenance
    val type: String? = null,       // Cargo Van / Box Truck / Sprinter Van
    val sort: VehicleSort = VehicleSort.RISK,
) {
    val activeCount: Int get() = listOfNotNull(tier, status, type).size
}

/** Pure filtering/sorting so it is easy to unit-test and works on cached (offline) data too. */
fun List<VehicleSummary>.applyFilters(f: VehicleFilters): List<VehicleSummary> {
    val q = f.query.trim().lowercase()
    return filter { v ->
        (q.isEmpty() || q in v.registration.lowercase() || q in v.makeModel.lowercase() || q in v.depot.lowercase()) &&
            (f.tier == null || v.riskTier == f.tier) &&
            (f.status == null || v.status == f.status) &&
            (f.type == null || v.vehicleType == f.type)
    }.let { list ->
        when (f.sort) {
            VehicleSort.RISK -> list.sortedByDescending { it.riskProbability }
            VehicleSort.HEALTH -> list.sortedBy { it.healthScore }
            VehicleSort.REGISTRATION -> list.sortedBy { it.registration }
            VehicleSort.ODOMETER -> list.sortedByDescending { it.odometerKm ?: 0 }
        }
    }
}

class VehiclesViewModel(private val repository: FleetRepository) : ViewModel() {
    private val _state = MutableStateFlow(ScreenState<List<VehicleSummary>>())
    val state: StateFlow<ScreenState<List<VehicleSummary>>> = _state.asStateFlow()

    private val _filters = MutableStateFlow(VehicleFilters())
    val filters: StateFlow<VehicleFilters> = _filters.asStateFlow()

    /** The list actually shown: loaded vehicles with the current filters applied. */
    val visible: StateFlow<List<VehicleSummary>> = combine(_state, _filters) { s, f -> s.data.orEmpty().applyFilters(f) }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    init {
        load()
    }

    fun load(refresh: Boolean = false) {
        _state.update { if (refresh) it.copy(refreshing = true) else it.copy(loading = it.data == null, error = null) }
        viewModelScope.launch { _state.update { it.with(repository.vehicles()) } }
    }

    fun updateFilters(transform: (VehicleFilters) -> VehicleFilters) = _filters.update(transform)

    companion object {
        val Factory = viewModelFactory { initializer { VehiclesViewModel(container.repository) } }
    }
}
