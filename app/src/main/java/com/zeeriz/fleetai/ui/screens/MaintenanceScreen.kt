package com.zeeriz.fleetai.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.PrimaryTabRow
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.zeeriz.fleetai.domain.model.MaintenanceRecord
import com.zeeriz.fleetai.domain.model.MaintenanceSummary
import com.zeeriz.fleetai.domain.model.ScheduleItem
import com.zeeriz.fleetai.presentation.HistoryState
import com.zeeriz.fleetai.presentation.MaintenanceTab
import com.zeeriz.fleetai.presentation.MaintenanceViewModel
import com.zeeriz.fleetai.ui.components.Banner
import com.zeeriz.fleetai.ui.components.DataStatusBanner
import com.zeeriz.fleetai.ui.components.EmptyState
import com.zeeriz.fleetai.ui.components.FleetCard
import com.zeeriz.fleetai.ui.components.FleetScaffold
import com.zeeriz.fleetai.ui.components.StatCard
import com.zeeriz.fleetai.ui.components.StateContent
import com.zeeriz.fleetai.ui.components.StatusChip
import com.zeeriz.fleetai.ui.components.StatusMapping
import com.zeeriz.fleetai.ui.theme.Tone
import com.zeeriz.fleetai.ui.theme.accent
import com.zeeriz.fleetai.ui.theme.container
import com.zeeriz.fleetai.utils.Format

@Composable
fun MaintenanceScreen(onOpenVehicle: (Int) -> Unit, viewModel: MaintenanceViewModel = viewModel(factory = MaintenanceViewModel.Factory)) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val history by viewModel.history.collectAsStateWithLifecycle()
    val tab by viewModel.tab.collectAsStateWithLifecycle()

    FleetScaffold(
        title = "Maintenance",
        subtitle = state.data?.summary?.let { "${it.overdue} overdue · ${it.dueSoon} due soon · ${it.vehiclesWithOverdue} vehicles affected" },
    ) { padding ->
        StateContent(state, onRetry = { viewModel.load() }, onRefresh = { viewModel.load(refresh = true) }, modifier = Modifier.padding(padding)) { data ->
            LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                if (state.offlineSince != null || state.error != null) item { DataStatusBanner(state) }
                item { SummaryGrid(data.summary) }
                item {
                    Banner(
                        "${Format.percent(data.summary.breakdownShare)} of all maintenance spend went to breakdown repairs. " +
                            "Servicing overdue vehicles on time is the cheapest way to cut it.",
                        Tone.INFO,
                    )
                }
                item {
                    PrimaryTabRow(selectedTabIndex = tab.ordinal, containerColor = MaterialTheme.colorScheme.background) {
                        MaintenanceTab.entries.forEach { t ->
                            val count = when (t) {
                                MaintenanceTab.OVERDUE -> data.overdue.size
                                MaintenanceTab.UPCOMING -> data.upcoming.size
                                MaintenanceTab.COMPLETED -> history.total
                            }
                            Tab(selected = tab == t, onClick = { viewModel.selectTab(t) }, text = { Text("${t.label} ($count)") })
                        }
                    }
                }
                when (tab) {
                    MaintenanceTab.OVERDUE -> scheduleList(data.overdue, "Nothing overdue", onOpenVehicle)
                    MaintenanceTab.UPCOMING -> scheduleList(data.upcoming, "Nothing due in the next 10% of any interval", onOpenVehicle)
                    MaintenanceTab.COMPLETED -> historyList(history, viewModel, onOpenVehicle)
                }
            }
        }
    }
}

@Composable
private fun SummaryGrid(s: MaintenanceSummary) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            StatCard("Overdue", Format.number(s.overdue), Icons.Filled.Warning, Modifier.weight(1f), tone = Tone.CRITICAL,
                supporting = "${s.vehiclesWithOverdue} vehicles")
            StatCard("Due soon", Format.number(s.dueSoon), Icons.Filled.DateRange, Modifier.weight(1f), tone = Tone.WARNING,
                supporting = "Within 10% of interval")
        }
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            StatCard("Completed (30d)", Format.number(s.completed30d), Icons.Filled.CheckCircle, Modifier.weight(1f), tone = Tone.SUCCESS,
                supporting = "${s.breakdowns365d} breakdowns in 12 months")
            StatCard("Spend (30d)", Format.rupeesShort(s.spend30d), Icons.Filled.Build, Modifier.weight(1f),
                supporting = "${Format.rupeesShort(s.spend365d)} in 12 months")
        }
    }
}

private fun androidx.compose.foundation.lazy.LazyListScope.scheduleList(
    items: List<ScheduleItem>,
    emptyText: String,
    onOpenVehicle: (Int) -> Unit,
) {
    if (items.isEmpty()) {
        item { EmptyState(title = emptyText, message = "Pull down to refresh.", icon = Icons.Filled.CheckCircle) }
    }
    items(items, key = { "${it.vehicleId}-${it.service}" }) { s -> ScheduleRow(s) { onOpenVehicle(s.vehicleId) } }
}

private fun androidx.compose.foundation.lazy.LazyListScope.historyList(
    history: HistoryState,
    viewModel: MaintenanceViewModel,
    onOpenVehicle: (Int) -> Unit,
) {
    item {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf(null to "All", "Preventive" to "Preventive", "Breakdown" to "Breakdown repairs").forEach { (kind, label) ->
                FilterChip(selected = history.kind == kind, onClick = { viewModel.setHistoryKind(kind) }, label = { Text(label) })
            }
        }
    }
    history.error?.let { item { Banner(it, Tone.CRITICAL) } }
    items(history.items, key = { it.id }) { r -> CompletedRow(r) { onOpenVehicle(r.vehicleId) } }
    item {
        Box(Modifier.fillMaxWidth().padding(vertical = 8.dp), contentAlignment = Alignment.Center) {
            when {
                history.loading -> CircularProgressIndicator(Modifier.size(28.dp))
                history.canLoadMore -> OutlinedButton(onClick = { viewModel.loadHistory() }) {
                    Text("Load more (${history.items.size} of ${Format.number(history.total)})")
                }
                history.items.isNotEmpty() -> Text("All ${Format.number(history.total)} records shown",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

@Composable
private fun ScheduleRow(s: ScheduleItem, onClick: () -> Unit) {
    val tone = StatusMapping.serviceTone(s.status)
    FleetCard(onClick = onClick, contentPadding = 14) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            ToneIcon(Icons.Filled.Build, tone)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(s.service, style = MaterialTheme.typography.titleSmall)
                    if (s.critical) {
                        Spacer(Modifier.width(6.dp))
                        StatusChip("Critical", Tone.NEUTRAL, dot = false)
                    }
                }
                Text("${s.registration} · ${s.depot}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            StatusChip(StatusMapping.serviceLabel(s.status), tone)
        }
        Spacer(Modifier.height(10.dp))
        Text(Format.dueText(s.dueInKm, s.dueInDays, s.overduePct), style = MaterialTheme.typography.bodyMedium, color = tone.accent())
        Row {
            Text(
                listOfNotNull(
                    s.lastDoneDate?.let { "Last done ${Format.date(it)}" },
                    s.intervalKm?.let { "every ${Format.number(it)} km" } ?: s.intervalDays?.let { "every ${Format.days(it)}" },
                ).joinToString(" · "),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.weight(1f),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text("~${Format.rupees(s.estimatedCost)}", style = MaterialTheme.typography.labelLarge)
        }
    }
}

@Composable
private fun CompletedRow(r: MaintenanceRecord, onClick: () -> Unit) {
    val breakdown = r.kind == "Breakdown"
    FleetCard(onClick = onClick, contentPadding = 14) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            ToneIcon(if (breakdown) Icons.Filled.Warning else Icons.Filled.CheckCircle, if (breakdown) Tone.CRITICAL else Tone.SUCCESS)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(r.service, style = MaterialTheme.typography.titleSmall)
                Text(
                    "${r.registration.orEmpty()} · ${Format.date(r.date)}" + (r.odometerKm?.let { " · ${Format.km(it.toDouble())}" } ?: ""),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(Format.rupees(r.cost), style = MaterialTheme.typography.labelLarge)
                StatusChip(if (breakdown) "Breakdown repair" else "Completed", if (breakdown) Tone.CRITICAL else Tone.SUCCESS, dot = false)
            }
        }
        val notes = r.notes
        if (!notes.isNullOrBlank() || r.downtimeDays > 0) {
            Spacer(Modifier.height(6.dp))
            Text(
                listOfNotNull(notes, if (r.downtimeDays > 0) "${Format.days(r.downtimeDays)} off the road" else null).joinToString(" · "),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun ToneIcon(icon: ImageVector, tone: Tone) {
    Box(Modifier.size(36.dp).clip(MaterialTheme.shapes.small).background(tone.container()), contentAlignment = Alignment.Center) {
        Icon(icon, contentDescription = null, tint = tone.accent(), modifier = Modifier.size(18.dp))
    }
}
