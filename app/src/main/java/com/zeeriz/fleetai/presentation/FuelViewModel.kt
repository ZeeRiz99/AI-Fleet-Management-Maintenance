package com.zeeriz.fleetai.presentation

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.zeeriz.fleetai.data.remote.ApiResult
import com.zeeriz.fleetai.data.repository.FleetRepository
import com.zeeriz.fleetai.domain.model.FuelAnomalies
import com.zeeriz.fleetai.domain.model.FuelCheckResult
import com.zeeriz.fleetai.domain.model.FuelSummary
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

enum class FuelGroupBy(val label: String) { VEHICLE("Vehicle"), DEPOT("Depot"), MODEL("Model") }

data class FuelData(val summary: FuelSummary, val anomalies: FuelAnomalies)

/** Form for the live AI fuel check ("is this fill-up normal for this vehicle?"). */
data class FuelCheckForm(
    val vehicleId: Int? = null,
    val registration: String = "",
    val distanceKm: String = "",
    val litres: String = "",
    val checking: Boolean = false,
    val result: FuelCheckResult? = null,
    val error: String? = null,
) {
    val distance: Double? get() = distanceKm.toDoubleOrNull()?.takeIf { it > 0 && it <= 2000 }
    val fuel: Double? get() = litres.toDoubleOrNull()?.takeIf { it > 0 && it <= 500 }
    val canCheck: Boolean get() = vehicleId != null && distance != null && fuel != null && !checking
}

internal fun <A, B, R> combineResults(a: ApiResult<A>, b: ApiResult<B>, build: (A, B) -> R): ApiResult<R> =
    combineResults(a, b, ApiResult.Success(Unit)) { x, y, _ -> build(x, y) }

class FuelViewModel(private val repository: FleetRepository) : ViewModel() {
    private val _state = MutableStateFlow(ScreenState<FuelData>())
    val state: StateFlow<ScreenState<FuelData>> = _state.asStateFlow()

    private val _days = MutableStateFlow(30)
    val days: StateFlow<Int> = _days.asStateFlow()

    private val _groupBy = MutableStateFlow(FuelGroupBy.VEHICLE)
    val groupBy: StateFlow<FuelGroupBy> = _groupBy.asStateFlow()

    private val _form = MutableStateFlow(FuelCheckForm())
    val form: StateFlow<FuelCheckForm> = _form.asStateFlow()

    init {
        load()
    }

    fun setDays(days: Int) {
        if (days == _days.value) return
        _days.value = days
        load(refresh = true)
    }

    fun setGroupBy(group: FuelGroupBy) {
        _groupBy.value = group
    }

    fun load(refresh: Boolean = false) {
        val days = _days.value
        _state.update { if (refresh) it.copy(refreshing = true) else it.copy(loading = it.data == null, error = null) }
        viewModelScope.launch {
            val result = coroutineScope {
                val summary = async { repository.fuelSummary(days) }
                // anomalies use at least 90 days so the list is never empty for short windows
                val anomalies = async { repository.fuelAnomalies(maxOf(days, 90)) }
                combineResults(summary.await(), anomalies.await(), ::FuelData)
            }
            _state.update { it.with(result) }
        }
    }

    fun updateForm(transform: (FuelCheckForm) -> FuelCheckForm) =
        _form.update { transform(it).copy(result = null, error = null) }

    fun runCheck() {
        val f = _form.value
        val vehicleId = f.vehicleId ?: return
        val distance = f.distance ?: return
        val litres = f.fuel ?: return
        _form.update { it.copy(checking = true, result = null, error = null) }
        viewModelScope.launch {
            when (val r = repository.fuelCheck(vehicleId, distance, litres)) {
                is ApiResult.Success -> _form.update { it.copy(checking = false, result = r.data) }
                is ApiResult.Failure -> _form.update { it.copy(checking = false, error = r.message) }
            }
        }
    }

    companion object {
        val Factory = viewModelFactory { initializer { FuelViewModel(container.repository) } }
    }
}
