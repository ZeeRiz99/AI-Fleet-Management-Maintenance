package com.zeeriz.fleetai.ui.screens

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.Clear
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.zeeriz.fleetai.domain.model.VehicleSummary
import com.zeeriz.fleetai.presentation.VehicleFilters
import com.zeeriz.fleetai.presentation.VehicleSort
import com.zeeriz.fleetai.presentation.VehiclesViewModel
import com.zeeriz.fleetai.ui.components.DataStatusBanner
import com.zeeriz.fleetai.ui.components.EmptyState
import com.zeeriz.fleetai.ui.components.FleetCard
import com.zeeriz.fleetai.ui.components.FleetIcons
import com.zeeriz.fleetai.ui.components.FleetScaffold
import com.zeeriz.fleetai.ui.components.StateContent
import com.zeeriz.fleetai.ui.components.StatusChip
import com.zeeriz.fleetai.ui.components.StatusMapping
import com.zeeriz.fleetai.ui.theme.Tone
import com.zeeriz.fleetai.ui.theme.accent
import com.zeeriz.fleetai.utils.Format

@Composable
fun VehiclesScreen(onOpenVehicle: (Int) -> Unit, viewModel: VehiclesViewModel = viewModel(factory = VehiclesViewModel.Factory)) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val filters by viewModel.filters.collectAsStateWithLifecycle()
    val visible by viewModel.visible.collectAsStateWithLifecycle()
    var sortMenu by remember { mutableStateOf(false) }

    FleetScaffold(
        title = "Vehicles",
        subtitle = state.data?.let { "${visible.size} of ${it.size} vehicles" },
        actions = {
            Box {
                TextButton(onClick = { sortMenu = true }) {
                    Icon(Icons.AutoMirrored.Filled.List, contentDescription = null)
                    Spacer(Modifier.width(6.dp))
                    Text(filters.sort.label)
                }
                DropdownMenu(expanded = sortMenu, onDismissRequest = { sortMenu = false }) {
                    VehicleSort.entries.forEach { sort ->
                        DropdownMenuItem(text = { Text(sort.label) }, onClick = {
                            viewModel.updateFilters { it.copy(sort = sort) }
                            sortMenu = false
                        })
                    }
                }
            }
        },
    ) { padding ->
        StateContent(state, onRetry = { viewModel.load() }, onRefresh = { viewModel.load(refresh = true) }, modifier = Modifier.padding(padding)) { all ->
            LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                item {
                    OutlinedTextField(
                        value = filters.query,
                        onValueChange = { q -> viewModel.updateFilters { it.copy(query = q) } },
                        placeholder = { Text("Search registration, model or depot") },
                        leadingIcon = { Icon(Icons.Filled.Search, contentDescription = null) },
                        trailingIcon = {
                            if (filters.query.isNotEmpty()) {
                                IconButton(onClick = { viewModel.updateFilters { it.copy(query = "") } }) {
                                    Icon(Icons.Filled.Clear, contentDescription = "Clear search")
                                }
                            }
                        },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
                item { FilterRow(filters, all) { transform -> viewModel.updateFilters(transform) } }
                if (state.offlineSince != null || state.error != null) item { DataStatusBanner(state) }
                if (visible.isEmpty()) {
                    item {
                        EmptyState(
                            title = "No vehicles match",
                            message = "Try a different search or clear the filters.",
                            icon = FleetIcons.Truck,
                            actionLabel = "Clear filters",
                            onAction = { viewModel.updateFilters { VehicleFilters(sort = it.sort) } },
                        )
                    }
                }
                items(visible, key = { it.id }) { v -> VehicleRow(v) { onOpenVehicle(v.id) } }
            }
        }
    }
}

@Composable
private fun FilterRow(filters: VehicleFilters, all: List<VehicleSummary>, update: ((VehicleFilters) -> VehicleFilters) -> Unit) {
    val types = remember(all) { all.map { it.vehicleType }.distinct().sorted() }
    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        listOf("High", "Medium", "Low").forEach { tier ->
            FilterChip(
                selected = filters.tier == tier,
                onClick = { update { it.copy(tier = if (it.tier == tier) null else tier) } },
                label = { Text("$tier risk") },
            )
        }
        FilterChip(
            selected = filters.status == "maintenance",
            onClick = { update { it.copy(status = if (it.status == "maintenance") null else "maintenance") } },
            label = { Text("In workshop") },
        )
        types.forEach { type ->
            FilterChip(
                selected = filters.type == type,
                onClick = { update { it.copy(type = if (it.type == type) null else type) } },
                label = { Text(type) },
            )
        }
    }
}

@Composable
private fun VehicleRow(v: VehicleSummary, onClick: () -> Unit) {
    FleetCard(onClick = onClick, contentPadding = 14) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(v.registration, style = MaterialTheme.typography.titleMedium)
                    if (v.status == "maintenance") {
                        Spacer(Modifier.width(8.dp))
                        StatusChip("In workshop", Tone.WARNING, dot = false)
                    }
                }
                Text(
                    "${v.makeModel} · ${v.vehicleType} · ${v.depot}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            StatusChip("${Format.percent(v.riskProbability)} risk", StatusMapping.riskTone(v.riskTier))
        }
        Spacer(Modifier.height(12.dp))
        HealthLine(v.healthScore, v.healthBand)
        v.nextService?.let { s ->
            Spacer(Modifier.height(8.dp))
            Text(
                "${s.service} · ${Format.dueText(s.dueInKm, s.dueInDays, s.overduePct)}",
                style = MaterialTheme.typography.bodySmall,
                color = StatusMapping.serviceTone(s.status).accent(),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        v.odometerKm?.let {
            Text("Odometer ${Format.km(it.toDouble())}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

/** "Health 72 · Good" with a coloured bar; reused on the detail screen. */
@Composable
fun HealthLine(score: Int, band: String, modifier: Modifier = Modifier) {
    val tone = StatusMapping.healthTone(band)
    Row(modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text("Health", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.width(10.dp))
        LinearProgressIndicator(
            progress = { score / 100f },
            modifier = Modifier.weight(1f).height(8.dp),
            color = tone.accent(),
            trackColor = MaterialTheme.colorScheme.surfaceVariant,
            strokeCap = StrokeCap.Round,
            drawStopIndicator = {},
        )
        Spacer(Modifier.width(10.dp))
        Text("$score · $band", style = MaterialTheme.typography.labelLarge, color = tone.accent())
    }
}
