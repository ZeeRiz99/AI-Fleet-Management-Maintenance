package com.zeeriz.fleetai.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.zeeriz.fleetai.presentation.TripsViewModel
import com.zeeriz.fleetai.ui.components.Banner
import com.zeeriz.fleetai.ui.components.ErrorState
import com.zeeriz.fleetai.ui.components.FleetCard
import com.zeeriz.fleetai.ui.components.FleetScaffold
import com.zeeriz.fleetai.ui.components.LoadingSkeleton
import com.zeeriz.fleetai.ui.components.SectionHeader
import com.zeeriz.fleetai.ui.components.StatusChip
import com.zeeriz.fleetai.ui.components.TripRow
import com.zeeriz.fleetai.ui.theme.Tone
import com.zeeriz.fleetai.utils.Format

@Composable
fun TripsScreen(onBack: () -> Unit, onOpenVehicle: (Int) -> Unit, viewModel: TripsViewModel = viewModel(factory = TripsViewModel.Factory)) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    FleetScaffold(title = "Trips", subtitle = if (state.total > 0) "${Format.number(state.total)} completed trips" else null, onBack = onBack) { padding ->
        when {
            state.loading && state.items.isEmpty() -> LoadingSkeleton(Modifier.padding(padding))
            state.items.isEmpty() && state.error != null -> ErrorState(
                "Couldn't load trips", state.error ?: "", Modifier.padding(padding), onRetry = { viewModel.load(reset = true) },
            )
            else -> LazyColumn(Modifier.padding(padding), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                state.offlineSince?.let { item { Banner("Offline — showing saved trips from ${Format.relative(it)}.", Tone.WARNING) } }
                item {
                    FleetCard {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            SectionHeader("Active trips", subtitle = state.note, modifier = Modifier.weight(1f))
                            StatusChip("${state.active} live", Tone.NEUTRAL)
                        }
                    }
                }
                item { SectionHeader("Completed trips", subtitle = "Newest first") }
                items(state.items, key = { it.id }) { t ->
                    FleetCard(contentPadding = 12) {
                        TripRow(t, modifier = Modifier.clickable { onOpenVehicle(t.vehicleId) })
                    }
                }
                item {
                    Box(Modifier.fillMaxWidth().padding(8.dp), contentAlignment = Alignment.Center) {
                        when {
                            state.loadingMore -> CircularProgressIndicator(Modifier.size(28.dp))
                            state.canLoadMore -> OutlinedButton(onClick = { viewModel.load(reset = false) }) {
                                Text("Load more (${Format.number(state.items.size)} of ${Format.number(state.total)})")
                            }
                            else -> Text("End of list", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
                state.error?.let { item { Banner(it, Tone.CRITICAL) } }
            }
        }
    }
}
