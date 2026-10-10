package com.zeeriz.fleetai.presentation

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.zeeriz.fleetai.data.remote.ApiResult
import com.zeeriz.fleetai.data.repository.FleetRepository
import com.zeeriz.fleetai.domain.model.MaintenanceRecord
import com.zeeriz.fleetai.domain.model.MaintenanceSummary
import com.zeeriz.fleetai.domain.model.ScheduleItem
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

enum class MaintenanceTab(val label: String) { OVERDUE("Overdue"), UPCOMING("Upcoming"), COMPLETED("Completed") }

data class MaintenanceOverview(
    val summary: MaintenanceSummary,
    val overdue: List<ScheduleItem>,
    val upcoming: List<ScheduleItem>,
)

data class HistoryState(
    val items: List<MaintenanceRecord> = emptyList(),
    val total: Int = 0,
    val kind: String? = null,          // null = all, "Preventive", "Breakdown"
    val loading: Boolean = false,
    val error: String? = null,
) {
    val canLoadMore: Boolean get() = items.size < total
}

/** Combines several calls into one result: fails if any fails, "offline" if any came from the cache. */
internal fun <A, B, C, R> combineResults(a: ApiResult<A>, b: ApiResult<B>, c: ApiResult<C>, build: (A, B, C) -> R): ApiResult<R> {
    val failure = listOf(a, b, c).filterIsInstance<ApiResult.Failure>().firstOrNull()
    if (failure != null) return failure
    val all = listOf(a, b, c).map { it as ApiResult.Success<*> }
    val cached = all.filter { it.fromCache }
    @Suppress("UNCHECKED_CAST")
    return ApiResult.Success(
        build((a as ApiResult.Success<A>).data, (b as ApiResult.Success<B>).data, (c as ApiResult.Success<C>).data),
        fromCache = cached.isNotEmpty(),
        savedAt = cached.mapNotNull { it.savedAt }.minOrNull(),
    )
}

class MaintenanceViewModel(private val repository: FleetRepository) : ViewModel() {
    private val _state = MutableStateFlow(ScreenState<MaintenanceOverview>())
    val state: StateFlow<ScreenState<MaintenanceOverview>> = _state.asStateFlow()

    private val _history = MutableStateFlow(HistoryState())
    val history: StateFlow<HistoryState> = _history.asStateFlow()

    private val _tab = MutableStateFlow(MaintenanceTab.OVERDUE)
    val tab: StateFlow<MaintenanceTab> = _tab.asStateFlow()

    init {
        load()
        loadHistory(reset = true)
    }

    fun selectTab(tab: MaintenanceTab) {
        _tab.value = tab
    }

    fun load(refresh: Boolean = false) {
        _state.update { if (refresh) it.copy(refreshing = true) else it.copy(loading = it.data == null, error = null) }
        viewModelScope.launch {
            val result = coroutineScope {
                val summary = async { repository.maintenanceSummary() }
                val overdue = async { repository.maintenanceSchedule("overdue") }
                val upcoming = async { repository.maintenanceSchedule("due_soon") }
                combineResults(summary.await(), overdue.await(), upcoming.await(), ::MaintenanceOverview)
            }
            _state.update { it.with(result) }
            if (refresh) loadHistory(reset = true)
        }
    }

    fun setHistoryKind(kind: String?) {
        if (_history.value.kind == kind) return
        _history.value = HistoryState(kind = kind)
        loadHistory(reset = true)
    }

    fun loadHistory(reset: Boolean = false) {
        val current = _history.value
        if (current.loading) return
        val offset = if (reset) 0 else current.items.size
        _history.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            when (val r = repository.maintenanceHistory(current.kind, offset)) {
                is ApiResult.Success -> _history.update {
                    it.copy(items = if (reset) r.data.items else it.items + r.data.items, total = r.data.total, loading = false)
                }
                is ApiResult.Failure -> _history.update { it.copy(loading = false, error = r.message) }
            }
        }
    }

    companion object {
        val Factory = viewModelFactory { initializer { MaintenanceViewModel(container.repository) } }
    }
}
