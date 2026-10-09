package com.zeeriz.fleetai.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccountCircle
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.zeeriz.fleetai.BuildConfig
import com.zeeriz.fleetai.data.local.ThemeMode
import com.zeeriz.fleetai.presentation.SettingsViewModel
import com.zeeriz.fleetai.ui.components.FleetCard
import com.zeeriz.fleetai.ui.components.FleetScaffold
import com.zeeriz.fleetai.ui.components.InfoRow
import com.zeeriz.fleetai.ui.components.SectionHeader

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProfileScreen(viewModel: SettingsViewModel = viewModel(factory = SettingsViewModel.Factory)) {
    val settings by viewModel.settings.collectAsStateWithLifecycle()
    var serverDraft by remember { mutableStateOf(settings.serverUrl) }
    LaunchedEffect(settings.serverUrl) { serverDraft = settings.serverUrl }

    FleetScaffold(title = "Profile") { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            FleetCard {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Filled.AccountCircle, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(settings.fullName ?: "Not signed in", style = MaterialTheme.typography.titleMedium)
                        Text(
                            settings.username?.let { "@$it" } ?: "Sign-in arrives with the API (phase 3)",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    if (settings.isLoggedIn) TextButton(onClick = viewModel::signOut) { Text("Sign out") }
                }
            }

            SectionHeader("Appearance")
            FleetCard {
                Text("Theme", style = MaterialTheme.typography.titleSmall)
                Spacer(Modifier.height(10.dp))
                val modes = ThemeMode.entries
                SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                    modes.forEachIndexed { index, mode ->
                        SegmentedButton(
                            selected = settings.themeMode == mode,
                            onClick = { viewModel.setThemeMode(mode) },
                            shape = SegmentedButtonDefaults.itemShape(index = index, count = modes.size),
                        ) { Text(mode.name.lowercase().replaceFirstChar { it.uppercase() }) }
                    }
                }
            }

            SectionHeader("Server", subtitle = "FastAPI backend address")
            FleetCard {
                OutlinedTextField(
                    value = serverDraft,
                    onValueChange = { serverDraft = it },
                    label = { Text("API base URL") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                    supportingText = { Text("Emulator: http://10.0.2.2:8000 · Phone on same Wi-Fi: http://<laptop-ip>:8000") },
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(
                        onClick = { viewModel.setServerUrl(serverDraft) },
                        enabled = serverDraft.isNotBlank() && serverDraft.trim().trimEnd('/') != settings.serverUrl,
                    ) { Text("Save") }
                    TextButton(onClick = { viewModel.setServerUrl(BuildConfig.DEFAULT_API_URL) }) { Text("Reset to default") }
                }
            }

            SectionHeader("About")
            FleetCard {
                InfoRow("App version", BuildConfig.VERSION_NAME)
                HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                InfoRow("Data", "Simulated fleet (2023–2025)")
            }
        }
    }
}
