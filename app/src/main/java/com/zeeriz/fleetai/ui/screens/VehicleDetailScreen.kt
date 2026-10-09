package com.zeeriz.fleetai.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.zeeriz.fleetai.domain.model.MaintenanceRecord
import com.zeeriz.fleetai.domain.model.Prediction
import com.zeeriz.fleetai.domain.model.ScheduleItem
import com.zeeriz.fleetai.domain.model.Trip
import com.zeeriz.fleetai.domain.model.VehicleDetail
import com.zeeriz.fleetai.presentation.VehicleDetailViewModel
import com.zeeriz.fleetai.presentation.VehicleEvent
import com.zeeriz.fleetai.ui.components.DataStatusBanner
import com.zeeriz.fleetai.ui.components.FleetCard
import com.zeeriz.fleetai.ui.components.FleetIcons
import com.zeeriz.fleetai.ui.components.FleetScaffold
import com.zeeriz.fleetai.ui.components.InfoRow
import com.zeeriz.fleetai.ui.components.LineChart
import com.zeeriz.fleetai.ui.components.SectionHeader
import com.zeeriz.fleetai.ui.components.StateContent
import com.zeeriz.fleetai.ui.components.StatusChip
import com.zeeriz.fleetai.ui.components.StatusMapping
import com.zeeriz.fleetai.ui.theme.Tone
import com.zeeriz.fleetai.ui.theme.accent
import com.zeeriz.fleetai.ui.theme.container
import com.zeeriz.fleetai.ui.theme.onContainer
import com.zeeriz.fleetai.utils.Format
import kotlin.math.abs

@Composable
fun VehicleDetailScreen(onBack: () -> Unit, viewModel: VehicleDetailViewModel = viewModel(factory = VehicleDetailViewModel.Factory)) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val busy by viewModel.busy.collectAsStateWithLifecycle()
    val event by viewModel.event.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }
    var confirmService by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(event) {
        when (val e = event) {
            is VehicleEvent.Rescored -> { snackbar.showSnackbar("Model re-run: ${e.riskPercent}% breakdown risk"); viewModel.consumeEvent() }
            is VehicleEvent.Failed -> { snackbar.showSnackbar(e.message); viewModel.consumeEvent() }
            else -> Unit
        }
    }

    FleetScaffold(
        title = state.data?.registration ?: "Vehicle",
        subtitle = state.data?.let { "${it.makeModel} · ${it.depot}" },
        onBack = onBack,
        snackbarHostState = snackbar,
    ) { padding ->
        StateContent(state, onRetry = { viewModel.load() }, onRefresh = { viewModel.load(refresh = true) }, modifier = Modifier.padding(padding)) { v ->
            LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                if (state.offlineSince != null || state.error != null) item { DataStatusBanner(state) }
                item { HeaderCard(v) }
                item {
                    AiPredictionCard(
                        p = v.prediction,
                        busy = busy,
                        onRerun = viewModel::rerunModel,
                        onMarkDone = { confirmService = v.prediction.recommendation.service },
                    )
                }
                item { FuelEfficiencyCard(v) }
                item { UpcomingServicesCard(v.upcomingServices) }
                item { MaintenanceHistoryCard(v) }
                item { RecentTripsCard(v.recentTrips) }
            }
        }
    }

    confirmService?.let { service ->
        AlertDialog(
            onDismissRequest = { confirmService = null },
            icon = { Icon(Icons.Filled.Build, contentDescription = null) },
            title = { Text("Record $service as done?") },
            text = {
                Text("This adds a completed $service at the current odometer (simulation date ${Format.date("2025-12-31")}) " +
                    "and re-runs the AI model so you can see how the breakdown risk changes.")
            },
            confirmButton = {
                Button(onClick = { viewModel.recordService(service); confirmService = null }) { Text("Record & re-score") }
            },
            dismissButton = { TextButton(onClick = { confirmService = null }) { Text("Cancel") } },
        )
    }

    (event as? VehicleEvent.ServiceRecorded)?.let { e ->
        val before = e.result.before
        val after = e.result.after
        AlertDialog(
            onDismissRequest = viewModel::consumeEvent,
            icon = { Icon(Icons.Filled.CheckCircle, contentDescription = null, tint = Tone.SUCCESS.accent()) },
            title = { Text("${e.result.record.service} recorded") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("The AI model was re-run with the new service history:")
                    InfoRow("Breakdown risk", "${Format.percent(before.riskProbability)} → ${Format.percent(after.riskProbability)}",
                        valueTone = if (after.riskProbability < before.riskProbability) Tone.SUCCESS else Tone.WARNING)
                    InfoRow("Risk tier", "${before.riskTier} → ${after.riskTier}")
                    InfoRow("Health score", "${before.healthScore} → ${after.healthScore}")
                    InfoRow("Service cost", Format.rupees(e.result.record.cost))
                }
            },
            confirmButton = { Button(onClick = viewModel::consumeEvent) { Text("OK") } },
        )
    }
}

@Composable
private fun HeaderCard(v: VehicleDetail) {
    FleetCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier.size(44.dp).clip(MaterialTheme.shapes.medium).background(Tone.BRAND.container()),
                contentAlignment = Alignment.Center,
            ) { Icon(FleetIcons.Truck, contentDescription = null, tint = Tone.BRAND.accent()) }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(v.registration, style = MaterialTheme.typography.titleLarge)
                Text("${v.makeModel} · ${v.year} · ${v.fuelType}", style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            StatusChip(StatusMapping.vehicleStatusLabel(v.status), if (v.status == "maintenance") Tone.WARNING else Tone.SUCCESS)
        }
        Spacer(Modifier.height(12.dp))
        InfoRow("Type", v.vehicleType)
        InfoRow("Depot", v.depot)
        InfoRow("Mileage (odometer)", v.odometerKm?.let { Format.km(it.toDouble()) } ?: "-")
        InfoRow("Rated efficiency", "${Format.decimal(v.ratedKmPerL, 2)} km/l")
        Spacer(Modifier.height(8.dp))
        HealthLine(v.healthScore, v.healthBand)
    }
}

@Composable
private fun AiPredictionCard(p: Prediction, busy: Boolean, onRerun: () -> Unit, onMarkDone: () -> Unit) {
    val tone = StatusMapping.riskTone(p.riskTier)
    FleetCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(FleetIcons.Sparkle, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(8.dp))
            Text("AI prediction", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
            if (busy) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
        }
        Spacer(Modifier.height(12.dp))
        Surface(color = tone.container(), shape = MaterialTheme.shapes.large) {
            Row(Modifier.fillMaxWidth().padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("AI Maintenance Risk", style = MaterialTheme.typography.labelLarge, color = tone.onContainer())
                    Text(Format.percent(p.riskProbability), style = MaterialTheme.typography.headlineMedium,
                        color = tone.onContainer(), fontWeight = FontWeight.Bold)
                    Text("chance of a breakdown in the next 30 days", style = MaterialTheme.typography.bodySmall, color = tone.onContainer())
                }
                Column(horizontalAlignment = Alignment.End) {
                    StatusChip("${p.riskTier} risk", tone)
                    Spacer(Modifier.height(8.dp))
                    Text("Health ${p.healthScore}/100", style = MaterialTheme.typography.labelLarge, color = tone.onContainer())
                }
            }
        }
        Spacer(Modifier.height(14.dp))
        Text("Why?", style = MaterialTheme.typography.titleSmall)
        Spacer(Modifier.height(4.dp))
        Text(p.explanation, style = MaterialTheme.typography.bodyMedium)
        Spacer(Modifier.height(12.dp))
        val maxImpact = p.factors.maxOfOrNull { abs(it.impact) }?.takeIf { it > 0 } ?: 1.0
        p.factors.forEach { f ->
            val fTone = if (f.impact > 0) Tone.CRITICAL else Tone.SUCCESS
            Column(Modifier.padding(vertical = 5.dp)) {
                Row {
                    Text(f.label.replaceFirstChar { it.uppercase() }, style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f),
                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(f.display, style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.Medium)
                }
                Spacer(Modifier.height(3.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.weight(1f).height(6.dp).clip(MaterialTheme.shapes.small).background(MaterialTheme.colorScheme.surfaceVariant)) {
                        Box(Modifier.fillMaxWidth((abs(f.impact) / maxImpact).toFloat()).fillMaxHeight().background(fTone.accent()))
                    }
                    Spacer(Modifier.width(8.dp))
                    Text(f.direction, style = MaterialTheme.typography.labelSmall, color = fTone.accent())
                }
            }
        }
        Spacer(Modifier.height(12.dp))
        val rec = p.recommendation
        Surface(color = MaterialTheme.colorScheme.surfaceVariant, shape = MaterialTheme.shapes.medium) {
            Column(Modifier.fillMaxWidth().padding(14.dp)) {
                Text("Recommendation", style = MaterialTheme.typography.titleSmall)
                Spacer(Modifier.height(4.dp))
                Text(rec.text, style = MaterialTheme.typography.bodyMedium)
                Spacer(Modifier.height(8.dp))
                InfoRow("Service cost", Format.rupees(rec.serviceCost))
                InfoRow("Expected loss if ignored", Format.rupees(rec.expectedLoss))
                InfoRow("Net saving", Format.rupees(rec.netSaving), valueTone = if (rec.netSaving > 0) Tone.SUCCESS else Tone.NEUTRAL)
            }
        }
        Spacer(Modifier.height(12.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Button(onClick = onMarkDone, enabled = !busy, modifier = Modifier.weight(1f)) {
                Text("Mark service done", maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            OutlinedButton(onClick = onRerun, enabled = !busy) {
                Icon(Icons.Filled.Refresh, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(6.dp))
                Text("Re-run AI")
            }
        }
        Spacer(Modifier.height(8.dp))
        Text("${p.model} · scored ${p.scoredAt.replace('T', ' ')}", style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun FuelEfficiencyCard(v: VehicleDetail) {
    val f = v.fuel
    FleetCard {
        Text("Fuel consumption", style = MaterialTheme.typography.titleMedium)
        Text("Last 90 days", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.height(8.dp))
        InfoRow("Trips · distance", "${f.trips90d} · ${Format.km(f.km90d)}")
        InfoRow("Fuel used", "${Format.number(f.litres90d)} L · ${Format.rupees(f.cost90d)}")
        InfoRow("Average consumption", f.kmPerL90d?.let { "${Format.decimal(it, 2)} km/l (rated ${Format.decimal(v.ratedKmPerL, 2)})" } ?: "-")
        InfoRow("Cost per km", f.costPerKm90d?.let { "Rs ${Format.decimal(it)}" } ?: "-")
        if (f.monthlyKmPerL.size >= 2) {
            Spacer(Modifier.height(10.dp))
            Text("Efficiency (km/l), monthly", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            LineChart(values = f.monthlyKmPerL.map { it.kmPerL }, labels = f.monthlyKmPerL.map { Format.month(it.month) },
                format = { Format.decimal(it, 1) })
        }
    }
}

@Composable
private fun UpcomingServicesCard(items: List<ScheduleItem>) {
    FleetCard {
        SectionHeader("Service schedule", subtitle = "Every service type, most urgent first")
        items.forEach { s ->
            Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(s.service, style = MaterialTheme.typography.titleSmall)
                    Text(
                        Format.dueText(s.dueInKm, s.dueInDays, s.overduePct) + (s.lastDoneDate?.let { " · last ${Format.date(it)}" } ?: ""),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                StatusChip(StatusMapping.serviceLabel(s.status), StatusMapping.serviceTone(s.status))
            }
        }
    }
}

@Composable
private fun MaintenanceHistoryCard(v: VehicleDetail) {
    val m = v.maintenance
    FleetCard {
        SectionHeader("Maintenance history & repair costs")
        InfoRow("Total spent", Format.rupees(m.totalCost))
        InfoRow("Preventive (${m.services} services)", Format.rupees(m.preventiveCost))
        InfoRow("Breakdown repairs (${m.breakdowns})", Format.rupees(m.breakdownCost), valueTone = if (m.breakdowns > 0) Tone.CRITICAL else null)
        Spacer(Modifier.height(8.dp))
        HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
        m.history.forEach { r -> RecordRow(r) }
    }
}

@Composable
private fun RecordRow(r: MaintenanceRecord) {
    Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(r.service, style = MaterialTheme.typography.titleSmall)
            Text(
                "${Format.date(r.date)}" + (r.odometerKm?.let { " · ${Format.km(it.toDouble())}" } ?: "") +
                    (if (r.downtimeDays > 0) " · ${Format.days(r.downtimeDays)} down" else ""),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Column(horizontalAlignment = Alignment.End) {
            Text(Format.rupees(r.cost), style = MaterialTheme.typography.labelLarge)
            StatusChip(r.kind, if (r.kind == "Breakdown") Tone.CRITICAL else Tone.INFO, dot = false)
        }
    }
}

@Composable
private fun RecentTripsCard(trips: List<Trip>) {
    FleetCard {
        SectionHeader("Recent trips")
        trips.forEach { t ->
            Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(t.route, style = MaterialTheme.typography.titleSmall)
                    Text("${Format.date(t.date)} · ${t.startTime}–${t.endTime} · ${t.driver}", style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(Format.km(t.distanceKm), style = MaterialTheme.typography.labelLarge)
                    Text("${Format.decimal(t.fuelLitres)} L", style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}
