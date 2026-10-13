package com.zeeriz.fleetai.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.zeeriz.fleetai.domain.model.Alert
import com.zeeriz.fleetai.presentation.AlertsViewModel
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
import com.zeeriz.fleetai.ui.theme.container
import com.zeeriz.fleetai.utils.Format

private fun categoryIcon(category: String): ImageVector = when (category) {
    "high_risk" -> Icons.Filled.Warning
    "maintenance_overdue", "maintenance_due" -> Icons.Filled.Build
    "fuel_anomaly" -> FleetIcons.Fuel
    "health_warning" -> FleetIcons.Gauge
    else -> Icons.Filled.Info
}

@Composable
fun AlertsScreen(onOpenVehicle: (Int) -> Unit, viewModel: AlertsViewModel = viewModel(factory = AlertsViewModel.Factory)) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val filter by viewModel.filter.collectAsStateWithLifecycle()
    val visible by viewModel.visible.collectAsStateWithLifecycle()
    val message by viewModel.message.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }
    LaunchedEffect(message) { message?.let { snackbar.showSnackbar(it); viewModel.consumeMessage() } }

    FleetScaffold(
        title = "Alerts",
        subtitle = state.data?.let { "${it.unread} unread of ${it.total}" },
        snackbarHostState = snackbar,
        actions = {
            if ((state.data?.unread ?: 0) > 0) TextButton(onClick = viewModel::markAllRead) { Text("Mark all read") }
        },
    ) { padding ->
        StateContent(state, onRetry = { viewModel.load() }, onRefresh = { viewModel.load(refresh = true) }, modifier = Modifier.padding(padding)) { data ->
            val counts = remember(data) { data.items.groupingBy { it.category }.eachCount() }
            LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                if (state.offlineSince != null || state.error != null) item { DataStatusBanner(state) }
                item {
                    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        FilterChip(selected = filter.unreadOnly, onClick = { viewModel.setFilter { it.copy(unreadOnly = !it.unreadOnly) } },
                            label = { Text("Unread (${data.unread})") })
                        FilterChip(selected = filter.category == null, onClick = { viewModel.setFilter { it.copy(category = null) } },
                            label = { Text("All (${data.total})") })
                        StatusMapping.alertCategories.forEach { (key, label) ->
                            val n = counts[key] ?: 0
                            if (n > 0) {
                                FilterChip(
                                    selected = filter.category == key,
                                    onClick = { viewModel.setFilter { it.copy(category = if (it.category == key) null else key) } },
                                    label = { Text("$label ($n)") },
                                )
                            }
                        }
                    }
                }
                if (visible.isEmpty()) {
                    item {
                        EmptyState(
                            title = if (filter.unreadOnly) "You're all caught up" else "No alerts here",
                            message = "Nothing matches the current filter.",
                            icon = Icons.Filled.CheckCircle,
                        )
                    }
                }
                items(visible, key = { it.id }) { a ->
                    AlertCard(
                        a,
                        onOpen = {
                            viewModel.markRead(a)
                            a.vehicleId?.let(onOpenVehicle)
                        },
                        onMarkRead = { viewModel.markRead(a) },
                    )
                }
            }
        }
    }
}

@Composable
private fun AlertCard(a: Alert, onOpen: () -> Unit, onMarkRead: () -> Unit) {
    val tone = StatusMapping.severityTone(a.severity)
    FleetCard(onClick = onOpen, contentPadding = 14) {
        Row(verticalAlignment = Alignment.Top) {
            Box(Modifier.size(38.dp).clip(MaterialTheme.shapes.small).background(tone.container()), contentAlignment = Alignment.Center) {
                Icon(categoryIcon(a.category), contentDescription = null, tint = tone.accent(), modifier = Modifier.size(20.dp))
            }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        a.title,
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = if (a.read) FontWeight.Normal else FontWeight.SemiBold,
                        color = if (a.read) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.onSurface,
                        modifier = Modifier.weight(1f),
                    )
                    if (!a.read) Box(Modifier.size(8.dp).clip(CircleShape).background(MaterialTheme.colorScheme.primary))
                }
                Spacer(Modifier.height(2.dp))
                Text(a.message, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Spacer(Modifier.height(8.dp))
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    StatusChip(StatusMapping.categoryLabel(a.category), tone, dot = false)
                    Text(Format.date(a.date), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.weight(1f))
                    if (!a.read) {
                        TextButton(onClick = onMarkRead) {
                            Icon(Icons.Filled.Notifications, contentDescription = null, modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("Mark read")
                        }
                    }
                }
            }
        }
    }
}
