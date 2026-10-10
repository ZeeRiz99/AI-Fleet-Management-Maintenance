package com.zeeriz.fleetai.ui.screens

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.zeeriz.fleetai.domain.model.FuelAnomaly
import com.zeeriz.fleetai.domain.model.FuelGroup
import com.zeeriz.fleetai.domain.model.FuelSummary
import com.zeeriz.fleetai.presentation.FuelCheckForm
import com.zeeriz.fleetai.presentation.FuelData
import com.zeeriz.fleetai.presentation.FuelGroupBy
import com.zeeriz.fleetai.presentation.FuelViewModel
import com.zeeriz.fleetai.ui.components.Banner
import com.zeeriz.fleetai.ui.components.BarChart
import com.zeeriz.fleetai.ui.components.DataStatusBanner
import com.zeeriz.fleetai.ui.components.FleetCard
import com.zeeriz.fleetai.ui.components.FleetIcons
import com.zeeriz.fleetai.ui.components.FleetScaffold
import com.zeeriz.fleetai.ui.components.InfoRow
import com.zeeriz.fleetai.ui.components.LineChart
import com.zeeriz.fleetai.ui.components.SectionHeader
import com.zeeriz.fleetai.ui.components.StatCard
import com.zeeriz.fleetai.ui.components.StateContent
import com.zeeriz.fleetai.ui.components.StatusChip
import com.zeeriz.fleetai.ui.theme.Tone
import com.zeeriz.fleetai.ui.theme.accent
import com.zeeriz.fleetai.ui.theme.container
import com.zeeriz.fleetai.ui.theme.onContainer
import com.zeeriz.fleetai.utils.Format

private val PERIODS = listOf(7, 30, 90, 365)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FuelScreen(onBack: () -> Unit, onOpenVehicle: (Int) -> Unit, viewModel: FuelViewModel = viewModel(factory = FuelViewModel.Factory)) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val days by viewModel.days.collectAsStateWithLifecycle()
    val groupBy by viewModel.groupBy.collectAsStateWithLifecycle()
    val form by viewModel.form.collectAsStateWithLifecycle()

    FleetScaffold(title = "Fuel analytics", subtitle = "Consumption, cost and AI anomaly detection", onBack = onBack) { padding ->
        StateContent(state, onRetry = { viewModel.load() }, onRefresh = { viewModel.load(refresh = true) }, modifier = Modifier.padding(padding)) { data ->
            LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                item {
                    SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                        PERIODS.forEachIndexed { i, d ->
                            SegmentedButton(
                                selected = days == d,
                                onClick = { viewModel.setDays(d) },
                                shape = SegmentedButtonDefaults.itemShape(index = i, count = PERIODS.size),
                            ) { Text(if (d == 365) "1 year" else "$d days") }
                        }
                    }
                }
                if (state.offlineSince != null || state.error != null) item { DataStatusBanner(state) }
                item { TotalsGrid(data.summary) }
                item { TrendCard(data.summary) }
                item { BreakdownCard(data.summary, groupBy, viewModel::setGroupBy, onOpenVehicle) }
                item { AnomalyHeader(data) }
                items(data.anomalies.items.take(25), key = { it.tripId }) { a -> AnomalyRow(a) { onOpenVehicle(a.vehicleId) } }
                item { FuelCheckCard(data.summary, form, viewModel::updateForm, viewModel::runCheck) }
            }
        }
    }
}

@Composable
private fun TotalsGrid(s: FuelSummary) {
    val t = s.totals
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            StatCard("Fuel cost", Format.rupeesShort(t.cost), FleetIcons.Fuel, Modifier.weight(1f), supporting = "${Format.number(t.trips)} trips")
            StatCard("Fuel used", "${Format.number(t.litres)} L", FleetIcons.Fuel, Modifier.weight(1f), tone = Tone.INFO,
                supporting = Format.km(t.km))
        }
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            StatCard("Average", t.kmPerLitre?.let { "${Format.decimal(it, 2)} km/l" } ?: "-", FleetIcons.Gauge, Modifier.weight(1f),
                tone = Tone.SUCCESS, supporting = t.litresPer100Km?.let { "${Format.decimal(it)} L / 100 km" })
            StatCard("Cost per km", t.costPerKm?.let { "Rs ${Format.decimal(it)}" } ?: "-", FleetIcons.Route, Modifier.weight(1f),
                tone = Tone.WARNING, supporting = "Fleet average")
        }
    }
}

@Composable
private fun TrendCard(s: FuelSummary) {
    FleetCard {
        Text("Monthly trend", style = MaterialTheme.typography.titleMedium)
        Text("Last ${s.monthly.size} months", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.height(12.dp))
        Text("Fuel cost (Rs)", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        BarChart(values = s.monthly.map { it.cost }, labels = s.monthly.map { Format.month(it.month) })
        Spacer(Modifier.height(14.dp))
        Text("Fleet efficiency (km/l)", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        val eff = s.monthly.filter { it.kmPerLitre != null }
        LineChart(values = eff.map { it.kmPerLitre!! }, labels = eff.map { Format.month(it.month) }, color = Tone.SUCCESS.accent(),
            format = { Format.decimal(it, 2) })
        val prices = s.priceMonthly.filter { it.diesel != null }
        if (prices.size >= 2) {
            Spacer(Modifier.height(14.dp))
            Text("Diesel price paid (Rs / litre)", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            LineChart(values = prices.map { it.diesel!! }, labels = prices.map { Format.month(it.month) }, color = Tone.WARNING.accent(),
                format = { Format.decimal(it, 0) })
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun BreakdownCard(s: FuelSummary, groupBy: FuelGroupBy, onGroup: (FuelGroupBy) -> Unit, onOpenVehicle: (Int) -> Unit) {
    val rows = when (groupBy) {
        FuelGroupBy.VEHICLE -> s.byVehicle.sortedByDescending { it.costPerKm ?: 0.0 }.take(12)
        FuelGroupBy.DEPOT -> s.byDepot.sortedByDescending { it.costPerKm ?: 0.0 }
        FuelGroupBy.MODEL -> s.byModel.sortedByDescending { it.costPerKm ?: 0.0 }
    }
    val maxCpk = rows.maxOfOrNull { it.costPerKm ?: 0.0 }?.takeIf { it > 0 } ?: 1.0
    FleetCard {
        SectionHeader("Cost per km", subtitle = if (groupBy == FuelGroupBy.VEHICLE) "12 most expensive vehicles to run" else "Highest first")
        Spacer(Modifier.height(8.dp))
        SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
            FuelGroupBy.entries.forEachIndexed { i, g ->
                SegmentedButton(selected = groupBy == g, onClick = { onGroup(g) },
                    shape = SegmentedButtonDefaults.itemShape(index = i, count = FuelGroupBy.entries.size)) { Text(g.label) }
            }
        }
        Spacer(Modifier.height(8.dp))
        rows.forEach { g -> GroupBar(g, maxCpk, onClick = g.vehicleId?.let { id -> { onOpenVehicle(id) } }) }
    }
}

@Composable
private fun GroupBar(g: FuelGroup, max: Double, onClick: (() -> Unit)?) {
    Column(
        Modifier.fillMaxWidth().then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier).padding(vertical = 7.dp),
    ) {
        Row {
            Text(g.name, style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(g.costPerKm?.let { "Rs ${Format.decimal(it)}/km" } ?: "-", style = MaterialTheme.typography.labelLarge)
        }
        Spacer(Modifier.height(4.dp))
        Box(Modifier.fillMaxWidth().height(8.dp).clip(MaterialTheme.shapes.small).background(MaterialTheme.colorScheme.surfaceVariant)) {
            Box(Modifier.fillMaxWidth(((g.costPerKm ?: 0.0) / max).toFloat()).fillMaxHeight().background(MaterialTheme.colorScheme.primary))
        }
        Text(
            "${Format.number(g.litres)} L · ${Format.km(g.km)} · ${g.kmPerLitre?.let { Format.decimal(it, 2) } ?: "-"} km/l · ${Format.rupeesShort(g.cost)}",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun AnomalyHeader(data: FuelData) {
    val a = data.anomalies
    Surface(color = Tone.WARNING.container(), shape = MaterialTheme.shapes.large) {
        Column(Modifier.fillMaxWidth().padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.Warning, contentDescription = null, tint = Tone.WARNING.accent())
                Spacer(Modifier.width(8.dp))
                Text("Abnormal fuel consumption detected", style = MaterialTheme.typography.titleMedium, color = Tone.WARNING.onContainer())
            }
            Spacer(Modifier.height(6.dp))
            Text(
                "${a.count} trips in the last ${a.days} days across ${a.vehiclesAffected} vehicles used " +
                    "${Format.number(a.excessLitres)} L more fuel than normal (about ${Format.rupees(a.excessCost)}).",
                style = MaterialTheme.typography.bodyMedium,
                color = Tone.WARNING.onContainer(),
            )
            Spacer(Modifier.height(6.dp))
            Text("How: ${a.method}", style = MaterialTheme.typography.bodySmall, color = Tone.WARNING.onContainer())
        }
    }
}

@Composable
private fun AnomalyRow(a: FuelAnomaly, onOpenVehicle: () -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    FleetCard(onClick = { expanded = !expanded }, contentPadding = 14, modifier = Modifier.animateContentSize()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(a.registration ?: "Vehicle ${a.vehicleId}", style = MaterialTheme.typography.titleSmall)
                Text("${Format.date(a.date)} · ${a.route}" + (a.driver?.let { " · $it" } ?: ""), style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            Column(horizontalAlignment = Alignment.End) {
                Text("+${Format.decimal(a.excessLitres)} L", style = MaterialTheme.typography.titleSmall, color = Tone.CRITICAL.accent())
                Text(Format.rupees(a.excessCost), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        Spacer(Modifier.height(6.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            StatusChip("${Format.decimal(a.actualKmPerL, 2)} km/l", Tone.CRITICAL, dot = false)
            StatusChip("normal ${Format.decimal(a.baselineKmPerL, 2)}", Tone.NEUTRAL, dot = false)
        }
        if (expanded) {
            Spacer(Modifier.height(8.dp))
            Text("Why it was flagged", style = MaterialTheme.typography.labelLarge)
            Text(a.explanation, style = MaterialTheme.typography.bodySmall)
            Spacer(Modifier.height(6.dp))
            OutlinedButton(onClick = onOpenVehicle) { Text("Open vehicle") }
        }
    }
}

@Composable
private fun FuelCheckCard(
    s: FuelSummary,
    form: FuelCheckForm,
    update: ((FuelCheckForm) -> FuelCheckForm) -> Unit,
    onCheck: () -> Unit,
) {
    var menu by remember { mutableStateOf(false) }
    val vehicles = remember(s.byVehicle) { s.byVehicle.filter { it.vehicleId != null }.sortedBy { it.name } }
    FleetCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(FleetIcons.Sparkle, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(8.dp))
            Text("Check a fuel entry", style = MaterialTheme.typography.titleMedium)
        }
        Text("The AI compares the fill-up with this vehicle's own recent efficiency.", style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.height(12.dp))
        Box {
            OutlinedButton(onClick = { menu = true }, modifier = Modifier.fillMaxWidth()) {
                Text(form.registration.ifBlank { "Choose vehicle" }, modifier = Modifier.weight(1f))
                Icon(Icons.Filled.ArrowDropDown, contentDescription = null)
            }
            DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                vehicles.forEach { v ->
                    DropdownMenuItem(text = { Text(v.name) }, onClick = {
                        update { it.copy(vehicleId = v.vehicleId, registration = v.name) }
                        menu = false
                    })
                }
            }
        }
        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            OutlinedTextField(
                value = form.distanceKm, onValueChange = { v -> update { it.copy(distanceKm = v) } },
                label = { Text("Distance (km)") }, singleLine = true, modifier = Modifier.weight(1f),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
            )
            OutlinedTextField(
                value = form.litres, onValueChange = { v -> update { it.copy(litres = v) } },
                label = { Text("Fuel (litres)") }, singleLine = true, modifier = Modifier.weight(1f),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
            )
        }
        Spacer(Modifier.height(10.dp))
        Button(onClick = onCheck, enabled = form.canCheck, modifier = Modifier.fillMaxWidth()) {
            if (form.checking) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = MaterialTheme.colorScheme.onPrimary)
            else Text("Run AI check")
        }
        form.error?.let { Spacer(Modifier.height(8.dp)); Banner(it, Tone.CRITICAL) }
        form.result?.let { r ->
            val tone = if (r.abnormal) Tone.CRITICAL else Tone.SUCCESS
            Spacer(Modifier.height(12.dp))
            Surface(color = tone.container(), shape = MaterialTheme.shapes.medium) {
                Column(Modifier.fillMaxWidth().padding(14.dp)) {
                    Text(r.verdict, style = MaterialTheme.typography.titleLarge, color = tone.onContainer(), fontWeight = FontWeight.Bold)
                    Text(r.explanation, style = MaterialTheme.typography.bodyMedium, color = tone.onContainer())
                    Spacer(Modifier.height(6.dp))
                    InfoRow("Expected fuel", "${Format.decimal(r.expectedLitres)} L")
                    InfoRow("Extra fuel", "${Format.decimal(r.excessLitres)} L · ${Format.rupees(r.excessCost)}")
                }
            }
        }
    }
}
