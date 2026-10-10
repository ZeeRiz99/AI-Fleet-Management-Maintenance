package com.zeeriz.fleetai.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.zeeriz.fleetai.domain.model.DriverSummary
import com.zeeriz.fleetai.presentation.DriverDetailViewModel
import com.zeeriz.fleetai.presentation.DriverSort
import com.zeeriz.fleetai.presentation.DriversViewModel
import com.zeeriz.fleetai.presentation.sortDrivers
import com.zeeriz.fleetai.ui.components.DataStatusBanner
import com.zeeriz.fleetai.ui.components.FleetCard
import com.zeeriz.fleetai.ui.components.FleetScaffold
import com.zeeriz.fleetai.ui.components.InfoRow
import com.zeeriz.fleetai.ui.components.SectionHeader
import com.zeeriz.fleetai.ui.components.StateContent
import com.zeeriz.fleetai.ui.components.TripRow
import com.zeeriz.fleetai.ui.theme.Tone
import com.zeeriz.fleetai.ui.theme.accent
import com.zeeriz.fleetai.ui.theme.container
import com.zeeriz.fleetai.ui.theme.onContainer
import com.zeeriz.fleetai.utils.Format

private fun scoreTone(score: Int) = when {
    score >= 70 -> Tone.SUCCESS
    score >= 50 -> Tone.WARNING
    else -> Tone.CRITICAL
}

@Composable
fun DriversScreen(onBack: () -> Unit, onOpenDriver: (Int) -> Unit, viewModel: DriversViewModel = viewModel(factory = DriversViewModel.Factory)) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val sort by viewModel.sort.collectAsStateWithLifecycle()
    var menu by remember { mutableStateOf(false) }
    FleetScaffold(
        title = "Drivers",
        subtitle = state.data?.let { "${it.items.size} drivers · last ${it.days} days" },
        onBack = onBack,
        actions = {
            Box {
                TextButton(onClick = { menu = true }) {
                    Icon(Icons.AutoMirrored.Filled.List, contentDescription = null)
                    Spacer(Modifier.width(6.dp))
                    Text(sort.label)
                }
                DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                    DriverSort.entries.forEach { s ->
                        DropdownMenuItem(text = { Text(s.label) }, onClick = { viewModel.setSort(s); menu = false })
                    }
                }
            }
        },
    ) { padding ->
        StateContent(state, onRetry = { viewModel.load() }, onRefresh = { viewModel.load(refresh = true) }, modifier = Modifier.padding(padding)) { data ->
            LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                if (state.offlineSince != null || state.error != null) item { DataStatusBanner(state) }
                items(data.items.sortDrivers(sort), key = { it.id }) { d -> DriverRow(d) { onOpenDriver(d.id) } }
                item {
                    FleetCard {
                        Text("How the scores work", style = MaterialTheme.typography.titleSmall)
                        Spacer(Modifier.height(4.dp))
                        Text(data.safetyFormula, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Spacer(Modifier.height(4.dp))
                        Text(data.performanceFormula, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    }
}

@Composable
private fun DriverRow(d: DriverSummary, onClick: () -> Unit) {
    FleetCard(onClick = onClick, contentPadding = 14) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Initials(d.name, scoreTone(d.safetyScore))
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(d.name, style = MaterialTheme.typography.titleSmall)
                Text("${d.depot} · ${d.experienceYears} yrs experience", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, contentDescription = null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Spacer(Modifier.height(10.dp))
        ScoreLine("Safety", d.safetyScore)
        ScoreLine("Performance", d.performanceScore)
        Spacer(Modifier.height(4.dp))
        Text(
            "${Format.number(d.trips)} trips · ${Format.km(d.distanceKm)} · ${Format.decimal(d.harshPer100Km, 2)} harsh brakes/100 km" +
                (d.mostUsedVehicle?.let { " · mostly $it" } ?: ""),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun Initials(name: String, tone: Tone, size: Int = 40) {
    val letters = name.split(" ").filter { it.isNotBlank() }.take(2).joinToString("") { it.first().uppercase() }
    Box(Modifier.size(size.dp).clip(CircleShape).background(tone.container()), contentAlignment = Alignment.Center) {
        Text(letters, style = MaterialTheme.typography.titleSmall, color = tone.onContainer())
    }
}

@Composable
private fun ScoreLine(label: String, score: Int) {
    val tone = scoreTone(score)
    Row(Modifier.fillMaxWidth().padding(vertical = 3.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.width(92.dp))
        LinearProgressIndicator(
            progress = { score / 100f },
            modifier = Modifier.weight(1f).height(8.dp),
            color = tone.accent(),
            trackColor = MaterialTheme.colorScheme.surfaceVariant,
            strokeCap = StrokeCap.Round,
            drawStopIndicator = {},
        )
        Spacer(Modifier.width(10.dp))
        Text("$score", style = MaterialTheme.typography.labelLarge, color = tone.accent(), modifier = Modifier.width(28.dp))
    }
}

@Composable
fun DriverDetailScreen(
    onBack: () -> Unit,
    onOpenVehicle: (Int) -> Unit,
    viewModel: DriverDetailViewModel = viewModel(factory = DriverDetailViewModel.Factory),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    FleetScaffold(title = state.data?.name ?: "Driver", subtitle = state.data?.let { "${it.depot} depot" }, onBack = onBack) { padding ->
        StateContent(state, onRetry = { viewModel.load() }, onRefresh = { viewModel.load(refresh = true) }, modifier = Modifier.padding(padding)) { d ->
            LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                if (state.offlineSince != null || state.error != null) item { DataStatusBanner(state) }
                item {
                    FleetCard {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Initials(d.name, scoreTone(d.safetyScore), size = 52)
                            Spacer(Modifier.width(14.dp))
                            Column {
                                Text(d.name, style = MaterialTheme.typography.titleLarge)
                                Text("License ${d.licenseNumber}", style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                        Spacer(Modifier.height(12.dp))
                        InfoRow("Depot", d.depot)
                        InfoRow("Experience", "${d.experienceYears} years")
                        if (d.mostUsedVehicle != null && d.mostUsedVehicleId != null) {
                            Row(
                                Modifier.fillMaxWidth().clickable { onOpenVehicle(d.mostUsedVehicleId) }.padding(vertical = 6.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Text("Assigned vehicle (most driven)", style = MaterialTheme.typography.bodyMedium,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.weight(1f))
                                Text(d.mostUsedVehicle, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.primary)
                                Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                            }
                        }
                    }
                }
                item {
                    FleetCard {
                        SectionHeader("Scores", subtitle = "Last ${d.days} days")
                        Spacer(Modifier.height(6.dp))
                        ScoreLine("Safety", d.safetyScore)
                        ScoreLine("Performance", d.performanceScore)
                        Spacer(Modifier.height(8.dp))
                        InfoRow("Trips", Format.number(d.trips))
                        InfoRow("Distance travelled", Format.km(d.distanceKm))
                        InfoRow("Harsh braking", "${Format.decimal(d.harshPer100Km, 2)} per 100 km",
                            valueTone = scoreTone(d.safetyScore).takeIf { it != Tone.SUCCESS })
                        Spacer(Modifier.height(8.dp))
                        Text(d.safetyFormula, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(d.performanceFormula, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                item {
                    FleetCard {
                        SectionHeader("Recent trips")
                        d.recentTrips.forEach { t -> TripRow(t, showDriver = false, modifier = Modifier.clickable { onOpenVehicle(t.vehicleId) }) }
                    }
                }
            }
        }
    }
}
