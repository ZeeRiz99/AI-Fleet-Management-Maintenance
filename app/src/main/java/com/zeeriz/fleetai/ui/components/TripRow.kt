package com.zeeriz.fleetai.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.zeeriz.fleetai.domain.model.Trip
import com.zeeriz.fleetai.ui.theme.Tone
import com.zeeriz.fleetai.utils.Format

/** One trip: route, when, who/which vehicle, distance, fuel; flags abnormal fuel use. */
@Composable
fun TripRow(t: Trip, modifier: Modifier = Modifier, showVehicle: Boolean = true, showDriver: Boolean = true) {
    Column(modifier.fillMaxWidth().padding(vertical = 8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(t.route, style = MaterialTheme.typography.titleSmall)
                Text(
                    "${Format.date(t.date)} · ${t.startTime}–${t.endTime} (${t.durationMin / 60}h ${t.durationMin % 60}m)",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(Format.km(t.distanceKm), style = MaterialTheme.typography.labelLarge)
                Text("${Format.decimal(t.fuelLitres)} L · ${Format.rupees(t.fuelCost)}", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        val who = listOfNotNull(if (showVehicle) t.registration else null, if (showDriver) t.driver else null).joinToString(" · ")
        if (who.isNotEmpty() || t.fuelAnomaly || t.harshBrakingEvents > 0) {
            Spacer(Modifier.height(4.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                if (who.isNotEmpty()) {
                    Text(who, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.weight(1f, fill = false), maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                if (t.harshBrakingEvents > 0) StatusChip("${t.harshBrakingEvents} harsh brake${if (t.harshBrakingEvents == 1) "" else "s"}", Tone.WARNING, dot = false)
                if (t.fuelAnomaly) StatusChip("Fuel anomaly", Tone.CRITICAL, dot = false)
            }
        }
    }
}
