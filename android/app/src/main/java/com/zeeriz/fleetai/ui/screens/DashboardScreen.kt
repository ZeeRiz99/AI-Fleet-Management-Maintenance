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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.zeeriz.fleetai.domain.model.Alert
import com.zeeriz.fleetai.domain.model.Dashboard
import com.zeeriz.fleetai.domain.model.ScheduleItem
import com.zeeriz.fleetai.domain.model.VehicleSummary
import com.zeeriz.fleetai.presentation.DashboardViewModel
import com.zeeriz.fleetai.ui.components.DataStatusBanner
import com.zeeriz.fleetai.ui.components.FleetCard
import com.zeeriz.fleetai.ui.components.FleetIcons
import com.zeeriz.fleetai.ui.components.FleetScaffold
import com.zeeriz.fleetai.ui.components.LineChart
import com.zeeriz.fleetai.ui.components.SectionHeader
import com.zeeriz.fleetai.ui.components.SegmentedBar
import com.zeeriz.fleetai.ui.components.StatCard
import com.zeeriz.fleetai.ui.components.StateContent
import com.zeeriz.fleetai.ui.components.StatusChip
import com.zeeriz.fleetai.ui.components.StatusMapping
import com.zeeriz.fleetai.ui.theme.Tone
import com.zeeriz.fleetai.ui.theme.accent
import com.zeeriz.fleetai.ui.theme.container
import com.zeeriz.fleetai.utils.Format

data class DashboardActions(
    val openVehicle: (Int) -> Unit,
    val openVehicles: () -> Unit,
    val openMaintenance: () -> Unit,
    val openAlerts: () -> Unit,
    val openFuel: () -> Unit,
    val openDrivers: () -> Unit,
    val openTrips: () -> Unit,
    val openAssistant: () -> Unit,
)

@Composable
fun DashboardScreen(actions: DashboardActions, viewModel: DashboardViewModel = viewModel(factory = DashboardViewModel.Factory)) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    FleetScaffold(
        title = "Dashboard",
        subtitle = state.data?.let { "Scored as of ${Format.date(it.asOf)} · simulated fleet" },
        actions = { IconButton(onClick = { viewModel.load(refresh = true) }) { Icon(Icons.Filled.Refresh, "Refresh") } },
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = actions.openAssistant,
                // the label is not exposed to accessibility on its own (found by the CI UI check): TalkBack reads this
                modifier = Modifier.semantics { contentDescription = "Ask FleetLog AI" },
                icon = { Icon(FleetIcons.Sparkle, contentDescription = null) },
                text = { Text("Ask FleetLog AI") },
            )
        },
    ) { padding ->
        StateContent(
            state = state,
            onRetry = { viewModel.load() },
            onRefresh = { viewModel.load(refresh = true) },
            modifier = Modifier.padding(padding),
        ) { data ->
            // bottom padding keeps the last card clear of the "Ask FleetLog AI" button
            LazyColumn(
                contentPadding = PaddingValues(start = 16.dp, top = 16.dp, end = 16.dp, bottom = 88.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                if (state.offlineSince != null || state.error != null) item { DataStatusBanner(state) }
                item { FleetStatusGrid(data, actions) }
                item { QuickLinks(actions) }
                item { AiRiskCard(data, actions.openVehicle, actions.openVehicles) }
                item { HealthCard(data) }
                item { FuelCard(data, actions.openFuel) }
                item { UpcomingMaintenanceCard(data.maintenance.upcoming, data.maintenance.overdue, actions) }
                item { RecentAlertsCard(data.recentAlerts, data.unreadAlerts, actions) }
            }
        }
    }
}

@Composable
private fun FleetStatusGrid(d: Dashboard, actions: DashboardActions) {
    val f = d.fleet
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        SectionHeader("Fleet status", subtitle = "${f.totalVehicles} vehicles across ${f.depots} depots")
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            StatCard("Total vehicles", Format.number(f.totalVehicles), FleetIcons.Truck, Modifier.weight(1f),
                supporting = "${f.depots} depots", onClick = actions.openVehicles)
            StatCard("Active", Format.number(f.active), Icons.Filled.CheckCircle, Modifier.weight(1f), tone = Tone.SUCCESS,
                supporting = "On the road")
        }
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            StatCard("In maintenance", Format.number(f.inMaintenance), Icons.Filled.Build, Modifier.weight(1f), tone = Tone.WARNING,
                supporting = "Breakdown repair", onClick = actions.openMaintenance)
            StatCard("Critical", Format.number(f.critical), Icons.Filled.Warning, Modifier.weight(1f), tone = Tone.CRITICAL,
                supporting = "High breakdown risk", onClick = actions.openVehicles)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            StatCard("Drivers", Format.number(f.drivers), Icons.Filled.Person, Modifier.weight(1f), tone = Tone.INFO,
                supporting = "Safety & performance", onClick = actions.openDrivers)
            StatCard("Unread alerts", Format.number(d.unreadAlerts), Icons.Filled.Notifications, Modifier.weight(1f),
                tone = if (d.unreadAlerts > 0) Tone.CRITICAL else Tone.SUCCESS, supporting = "Tap to review",
                onClick = actions.openAlerts)
        }
    }
}

@Composable
private fun QuickLinks(actions: DashboardActions) {
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        QuickLink("Fuel", FleetIcons.Fuel, Modifier.weight(1f), actions.openFuel)
        QuickLink("Drivers", Icons.Filled.Person, Modifier.weight(1f), actions.openDrivers)
        QuickLink("Trips", FleetIcons.Route, Modifier.weight(1f), actions.openTrips)
    }
}

@Composable
private fun QuickLink(label: String, icon: androidx.compose.ui.graphics.vector.ImageVector, modifier: Modifier, onClick: () -> Unit) {
    FleetCard(modifier = modifier, onClick = onClick, contentPadding = 12) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(8.dp))
            Text(label, style = MaterialTheme.typography.labelLarge)
        }
    }
}

@Composable
private fun AiRiskCard(d: Dashboard, openVehicle: (Int) -> Unit, openVehicles: () -> Unit) {
    val r = d.risk
    FleetCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(FleetIcons.Sparkle, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(8.dp))
            Text("AI maintenance risk", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
            StatusChip("Next 30 days", Tone.BRAND, dot = false)
        }
        Spacer(Modifier.height(4.dp))
        Text(
            "XGBoost model on service history, mileage, age, fuel efficiency and engine sensors.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(14.dp))
        SegmentedBar(listOf(r.high to Tone.CRITICAL.accent(), r.medium to Tone.WARNING.accent(), r.low to Tone.SUCCESS.accent()))
        Spacer(Modifier.height(10.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            LegendDot("High", r.high, Tone.CRITICAL)
            LegendDot("Medium", r.medium, Tone.WARNING)
            LegendDot("Low", r.low, Tone.SUCCESS)
        }
        Spacer(Modifier.height(12.dp))
        Row {
            MiniMetric("Average risk", Format.percent(r.averageProbability), Modifier.weight(1f))
            MiniMetric("Possible saving", Format.rupeesShort(r.potentialSaving), Modifier.weight(1f))
        }
        Spacer(Modifier.height(12.dp))
        HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
        r.top.take(3).forEach { v -> RiskRow(v) { openVehicle(v.id) } }
        Row(
            Modifier.fillMaxWidth().clickable(onClick = openVehicles).padding(top = 10.dp),
            horizontalArrangement = Arrangement.End,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text("All vehicles", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
            Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
        }
    }
}

@Composable
private fun RiskRow(v: VehicleSummary, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().clickable(onClick = onClick).padding(vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(v.registration, style = MaterialTheme.typography.titleSmall)
            Text(
                "${v.makeModel} · ${v.depot}" + (v.nextService?.let { " · ${it.service}" } ?: ""),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        StatusChip("${Format.percent(v.riskProbability)} risk", StatusMapping.riskTone(v.riskTier))
    }
}

@Composable
private fun HealthCard(d: Dashboard) {
    val h = d.health
    FleetCard {
        Text("Vehicle health", style = MaterialTheme.typography.titleMedium)
        Spacer(Modifier.height(12.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(contentAlignment = Alignment.Center) {
                CircularProgressIndicator(
                    progress = { (h.average / 100).toFloat().coerceIn(0f, 1f) },
                    modifier = Modifier.size(84.dp),
                    strokeWidth = 9.dp,
                    color = StatusMapping.healthTone(if (h.average >= 70) "Good" else if (h.average >= 40) "Watch" else "Critical").accent(),
                    trackColor = MaterialTheme.colorScheme.surfaceVariant,
                    strokeCap = StrokeCap.Round,
                )
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(Format.decimal(h.average, 0), style = MaterialTheme.typography.titleLarge)
                    Text("avg", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            Spacer(Modifier.width(20.dp))
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                HealthBucket("Good (70+)", h.good, Tone.SUCCESS)
                HealthBucket("Watch (40-69)", h.watch, Tone.WARNING)
                HealthBucket("Critical (<40)", h.critical, Tone.CRITICAL)
            }
        }
        if (h.formula.isNotBlank()) {
            Spacer(Modifier.height(10.dp))
            Text(h.formula, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun HealthBucket(label: String, count: Int, tone: Tone) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(10.dp).clip(CircleShape).background(tone.accent()))
        Spacer(Modifier.width(8.dp))
        Text(label, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f))
        Text(Format.number(count), style = MaterialTheme.typography.titleSmall)
    }
}

@Composable
private fun FuelCard(d: Dashboard, openFuel: () -> Unit) {
    val f = d.fuel
    FleetCard(onClick = openFuel) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(FleetIcons.Fuel, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(8.dp))
            Text("Fuel consumption", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
            Text("Last 30 days", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Spacer(Modifier.height(12.dp))
        Row {
            MiniMetric("Fuel cost", Format.rupeesShort(f.cost), Modifier.weight(1f))
            MiniMetric("Litres", Format.number(f.litres), Modifier.weight(1f))
            MiniMetric("Cost / km", f.costPerKm?.let { "Rs " + Format.decimal(it) } ?: "-", Modifier.weight(1f))
        }
        Spacer(Modifier.height(14.dp))
        Text("Fuel cost per km (Rs), monthly", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.height(6.dp))
        val months = f.monthly.filter { it.costPerKm != null }
        LineChart(values = months.map { it.costPerKm!! }, labels = months.map { Format.month(it.month) })
        if (f.anomalies > 0) {
            Spacer(Modifier.height(10.dp))
            StatusChip("${f.anomalies} abnormal fuel trips · ${Format.rupeesShort(f.anomalyExcessCost)} extra", Tone.WARNING)
        }
    }
}

@Composable
private fun UpcomingMaintenanceCard(items: List<ScheduleItem>, overdue: Int, actions: DashboardActions) {
    FleetCard {
        SectionHeader("Upcoming maintenance", subtitle = "$overdue services overdue across the fleet",
            actionLabel = "See all", onAction = actions.openMaintenance)
        if (items.isEmpty()) {
            Text("Nothing due soon.", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        items.forEach { s ->
            Row(
                Modifier.fillMaxWidth().clickable { actions.openVehicle(s.vehicleId) }.padding(vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                IconBadge(Icons.Filled.Build, StatusMapping.serviceTone(s.status))
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(s.service, style = MaterialTheme.typography.titleSmall)
                    Text(
                        "${s.registration} · ${Format.dueText(s.dueInKm, s.dueInDays, s.overduePct)}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Text(Format.rupeesShort(s.estimatedCost), style = MaterialTheme.typography.labelLarge)
            }
        }
    }
}

@Composable
private fun RecentAlertsCard(alerts: List<Alert>, unread: Int, actions: DashboardActions) {
    FleetCard {
        SectionHeader("Recent alerts", subtitle = "$unread unread", actionLabel = "See all", onAction = actions.openAlerts)
        alerts.forEach { a ->
            Row(
                Modifier.fillMaxWidth().clickable { a.vehicleId?.let(actions.openVehicle) ?: actions.openAlerts() }.padding(vertical = 10.dp),
                verticalAlignment = Alignment.Top,
            ) {
                IconBadge(Icons.Filled.Warning, StatusMapping.severityTone(a.severity))
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(a.title, style = MaterialTheme.typography.titleSmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(a.message, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 2)
                }
            }
        }
    }
}

@Composable
private fun IconBadge(icon: androidx.compose.ui.graphics.vector.ImageVector, tone: Tone) {
    Box(Modifier.size(34.dp).clip(MaterialTheme.shapes.small).background(tone.container()), contentAlignment = Alignment.Center) {
        Icon(icon, contentDescription = null, tint = tone.accent(), modifier = Modifier.size(18.dp))
    }
}

@Composable
private fun LegendDot(label: String, count: Int, tone: Tone) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(8.dp).clip(CircleShape).background(tone.accent()))
        Spacer(Modifier.width(6.dp))
        Text("$label $count", style = MaterialTheme.typography.labelMedium)
    }
}

@Composable
private fun MiniMetric(label: String, value: String, modifier: Modifier = Modifier) {
    Column(modifier) {
        Text(label, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.titleMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}
