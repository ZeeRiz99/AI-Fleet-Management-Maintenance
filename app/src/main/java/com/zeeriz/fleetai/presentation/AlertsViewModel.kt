package com.zeeriz.fleetai.presentation

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.zeeriz.fleetai.data.remote.ApiResult
import com.zeeriz.fleetai.data.repository.FleetRepository
import com.zeeriz.fleetai.domain.model.Alert
import com.zeeriz.fleetai.domain.model.AlertList
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class AlertFilter(val category: String? = null, val unreadOnly: Boolean = false)

fun List<Alert>.applyFilter(f: AlertFilter): List<Alert> =
    filter { (f.category == null || it.category == f.category) && (!f.unreadOnly || !it.read) }

/** Marks alerts read locally (optimistic update) and keeps the unread count consistent. */
fun AlertList.markRead(ids: Set<String>): AlertList {
    val newlyRead = items.count { it.id in ids && !it.read }
    return copy(items = items.map { if (it.id in ids) it.copy(read = true) else it }, unread = (unread - newlyRead).coerceAtLeast(0))
}

class AlertsViewModel(private val repository: FleetRepository) : ViewModel() {
    private val _state = MutableStateFlow(ScreenState<AlertList>())
    val state: StateFlow<ScreenState<AlertList>> = _state.asStateFlow()

    private val _filter = MutableStateFlow(AlertFilter())
    val filter: StateFlow<AlertFilter> = _filter.asStateFlow()

    val visible: StateFlow<List<Alert>> = combine(_state, _filter) { s, f -> s.data?.items.orEmpty().applyFilter(f) }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    private val _message = MutableStateFlow<String?>(null)
    val message: StateFlow<String?> = _message.asStateFlow()

    init {
        load()
    }

    fun load(refresh: Boolean = false) {
        _state.update { if (refresh) it.copy(refreshing = true) else it.copy(loading = it.data == null, error = null) }
        viewModelScope.launch { _state.update { it.with(repository.alerts()) } }
    }

    fun setFilter(transform: (AlertFilter) -> AlertFilter) = _filter.update(transform)

    fun markRead(alert: Alert) {
        if (alert.read) return
        val before = _state.value.data ?: return
        _state.update { it.copy(data = before.markRead(setOf(alert.id))) }
        viewModelScope.launch {
            val r = repository.markAlertRead(alert.id)
            if (r is ApiResult.Failure) {
                _state.update { it.copy(data = before) }
                _message.value = r.message
            }
        }
    }

    fun markAllRead() {
        val before = _state.value.data ?: return
        if (before.unread == 0) return
        _state.update { it.copy(data = before.markRead(before.items.map { a -> a.id }.toSet())) }
        viewModelScope.launch {
            when (val r = repository.markAllAlertsRead()) {
                is ApiResult.Success -> _message.value = "All alerts marked as read"
                is ApiResult.Failure -> {
                    _state.update { it.copy(data = before) }
                    _message.value = r.message
                }
            }
        }
    }

    fun consumeMessage() {
        _message.value = null
    }

    companion object {
        val Factory = viewModelFactory { initializer { AlertsViewModel(container.repository) } }
    }
}
