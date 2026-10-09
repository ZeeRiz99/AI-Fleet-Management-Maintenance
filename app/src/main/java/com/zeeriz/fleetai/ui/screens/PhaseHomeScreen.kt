package com.zeeriz.fleetai.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
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
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import com.zeeriz.fleetai.navigation.Routes
import com.zeeriz.fleetai.ui.components.FleetCard
import com.zeeriz.fleetai.ui.components.FleetIcons
import com.zeeriz.fleetai.ui.components.FleetScaffold
import com.zeeriz.fleetai.ui.components.SectionHeader
import com.zeeriz.fleetai.ui.components.StatusChip
import com.zeeriz.fleetai.ui.theme.Tone

private data class Link(val title: String, val subtitle: String, val icon: ImageVector, val route: String)

/** Phase 1 home: confirms theme + navigation; replaced by the real dashboard in phase 3. */
@Composable
fun PhaseHomeScreen(onNavigate: (String) -> Unit) {
    val links = listOf(
        Link("Vehicle details", "Sample vehicle #46", FleetIcons.Truck, Routes.vehicleDetail(46)),
        Link("Fuel analytics", "Consumption, cost per km, anomalies", FleetIcons.Fuel, Routes.FUEL),
        Link("Drivers", "Profiles, safety and performance", FleetIcons.Gauge, Routes.DRIVERS),
        Link("Trips", "Recent trips", FleetIcons.Route, Routes.TRIPS),
        Link("Sign in", "Login screen", Icons.Filled.Lock, Routes.LOGIN),
    )
    FleetScaffold(title = "FleetAI", subtitle = "AI fleet management & maintenance") { padding ->
        LazyColumn(
            Modifier.padding(padding),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item { Hero() }
            item { SectionHeader("Navigation check", subtitle = "Phase 1 — app shell, theme and navigation") }
            items(links) { link ->
                FleetCard(onClick = { onNavigate(link.route) }, contentPadding = 14) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(link.icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                        Spacer(Modifier.width(14.dp))
                        Column(Modifier.weight(1f)) {
                            Text(link.title, style = MaterialTheme.typography.titleSmall)
                            Text(link.subtitle, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, contentDescription = null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    }
}

@Composable
private fun Hero() {
    Column(
        Modifier
            .fillMaxWidth()
            .clip(MaterialTheme.shapes.extraLarge)
            .background(Brush.linearGradient(listOf(Color(0xFF0B1220), Color(0xFF1E3A8A), Color(0xFF2563EB))))
            .padding(20.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(FleetIcons.Truck, contentDescription = null, tint = Color.White, modifier = Modifier.size(28.dp))
            Spacer(Modifier.width(10.dp))
            Text("Fleet Intelligence", style = MaterialTheme.typography.labelLarge, color = Color(0xFF93C5FD))
        }
        Spacer(Modifier.height(8.dp))
        Text("AI Fleet Management & Maintenance", style = MaterialTheme.typography.headlineSmall, color = Color.White)
        Spacer(Modifier.height(4.dp))
        Text(
            "Predict breakdowns, catch fuel anomalies and plan maintenance.",
            style = MaterialTheme.typography.bodyMedium,
            color = Color(0xFFCBD5E1),
        )
        Spacer(Modifier.height(14.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            StatusChip("Phase 1", Tone.INFO)
            StatusChip("Simulated data", Tone.WARNING)
        }
    }
}
