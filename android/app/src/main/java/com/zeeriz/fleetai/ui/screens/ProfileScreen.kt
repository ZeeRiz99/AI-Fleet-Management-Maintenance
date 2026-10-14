package com.zeeriz.fleetai.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.SnackbarHostState
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
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.zeeriz.fleetai.BuildConfig
import com.zeeriz.fleetai.data.local.DataSource
import com.zeeriz.fleetai.data.local.ThemeMode
import com.zeeriz.fleetai.domain.model.ModelInfo
import com.zeeriz.fleetai.presentation.SettingsViewModel
import com.zeeriz.fleetai.ui.components.Banner
import com.zeeriz.fleetai.ui.components.FleetCard
import com.zeeriz.fleetai.ui.components.FleetIcons
import com.zeeriz.fleetai.ui.components.FleetScaffold
import com.zeeriz.fleetai.ui.components.InfoRow
import com.zeeriz.fleetai.ui.components.SectionHeader
import com.zeeriz.fleetai.ui.theme.Tone
import com.zeeriz.fleetai.ui.theme.accent
import com.zeeriz.fleetai.ui.theme.container
import com.zeeriz.fleetai.ui.theme.onContainer
import com.zeeriz.fleetai.utils.Format

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProfileScreen(viewModel: SettingsViewModel = viewModel(factory = SettingsViewModel.Factory)) {
    val settings by viewModel.settings.collectAsStateWithLifecycle()
    val connection by viewModel.connection.collectAsStateWithLifecycle()
    val model by viewModel.model.collectAsStateWithLifecycle()
    val message by viewModel.message.collectAsStateWithLifecycle()
    val resetting by viewModel.resetting.collectAsStateWithLifecycle()
    val uri = LocalUriHandler.current
    val snackbar = remember { SnackbarHostState() }
    var serverDraft by remember { mutableStateOf(settings.serverUrl) }
    var confirmSignOut by remember { mutableStateOf(false) }
    var confirmReset by remember { mutableStateOf(false) }
    LaunchedEffect(settings.serverUrl) { serverDraft = settings.serverUrl }
    LaunchedEffect(message) { message?.let { snackbar.showSnackbar(it); viewModel.consumeMessage() } }
    val gitHub = settings.dataSource == DataSource.GITHUB

    FleetScaffold(title = "Profile", subtitle = "Account, settings and AI model", snackbarHostState = snackbar) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            // ---------------------------------------------------------------- account
            FleetCard {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    val name = if (gitHub) "Demo viewer" else settings.fullName ?: settings.username ?: "?"
                    Box(Modifier.size(48.dp).clip(CircleShape).background(Tone.BRAND.container()), contentAlignment = Alignment.Center) {
                        Text(name.split(" ").take(2).joinToString("") { it.take(1).uppercase() },
                            style = MaterialTheme.typography.titleMedium, color = Tone.BRAND.onContainer())
                    }
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(name.takeIf { it != "?" } ?: "Signed in", style = MaterialTheme.typography.titleMedium)
                        Text(if (gitHub) "Read-only data from GitHub · no account needed" else settings.username?.let { "@$it" } ?: "",
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    if (!gitHub && settings.isLoggedIn) TextButton(onClick = { confirmSignOut = true }) { Text("Sign out") }
                }
            }

            // ---------------------------------------------------------------- appearance
            SectionHeader("Appearance")
            FleetCard {
                Text("Theme", style = MaterialTheme.typography.titleSmall)
                Spacer(Modifier.height(10.dp))
                SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                    ThemeMode.entries.forEachIndexed { index, mode ->
                        SegmentedButton(
                            selected = settings.themeMode == mode,
                            onClick = { viewModel.setThemeMode(mode) },
                            shape = SegmentedButtonDefaults.itemShape(index = index, count = ThemeMode.entries.size),
                        ) { Text(mode.name.lowercase().replaceFirstChar { it.uppercase() }) }
                    }
                }
            }

            // ---------------------------------------------------------------- data source
            SectionHeader("Data source", subtitle = "Where the fleet data and AI results come from")
            FleetCard {
                SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                    listOf(DataSource.GITHUB to "GitHub data", DataSource.SERVER to "Live server").forEachIndexed { index, (source, label) ->
                        SegmentedButton(
                            selected = settings.dataSource == source,
                            onClick = { viewModel.setDataSource(source) },
                            shape = SegmentedButtonDefaults.itemShape(index = index, count = 2),
                        ) { Text(label) }
                    }
                }
                Spacer(Modifier.height(10.dp))
                Text(
                    if (gitHub) "Published snapshot of the API: real XGBoost risk scores, SHAP reasons and fleet data, readable on " +
                        "any phone without a server. The fuel check runs on the phone. Recording a service and re-running the " +
                        "model need the live server."
                    else "The FastAPI backend: everything is live, including recording a service so the AI re-scores the vehicle. " +
                        "Needs the server running and a sign-in.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                if (gitHub) {
                    Spacer(Modifier.height(10.dp))
                    Button(onClick = viewModel::testConnection, enabled = !connection.checking) {
                        if (connection.checking) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = MaterialTheme.colorScheme.onPrimary)
                        else Text("Check data connection")
                    }
                    connection.text?.let {
                        Spacer(Modifier.height(10.dp))
                        Banner(it, if (connection.ok == true) Tone.SUCCESS else Tone.CRITICAL)
                    }
                }
            }

            // ---------------------------------------------------------------- server
            if (!gitHub) {
                SectionHeader("Server", subtitle = "FastAPI backend address")
                FleetCard {
                    OutlinedTextField(
                        value = serverDraft,
                        onValueChange = { serverDraft = it },
                        label = { Text("API base URL") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                        supportingText = { Text("Emulator: http://10.0.2.2:8000 · Phone (USB): http://localhost:8000 · Wi-Fi: http://<laptop-ip>:8000") },
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Spacer(Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        OutlinedButton(
                            onClick = { viewModel.setServerUrl(serverDraft) },
                            enabled = serverDraft.isNotBlank() && serverDraft.trim().trimEnd('/') != settings.serverUrl,
                        ) { Text("Save") }
                        Button(onClick = viewModel::testConnection, enabled = !connection.checking) {
                            if (connection.checking) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = MaterialTheme.colorScheme.onPrimary)
                            else Text("Test connection")
                        }
                        TextButton(onClick = { viewModel.setServerUrl(BuildConfig.DEFAULT_API_URL) }) { Text("Default") }
                    }
                    connection.text?.let {
                        Spacer(Modifier.height(10.dp))
                        Banner(it, if (connection.ok == true) Tone.SUCCESS else Tone.CRITICAL)
                    }
                }
            }

            // ---------------------------------------------------------------- AI model
            SectionHeader("AI model", subtitle = "How predictions are made and how good they are")
            val info = model.data
            when {
                info != null -> ModelCard(info)
                model.loading -> FleetCard { CircularProgressIndicator(Modifier.size(24.dp)) }
                else -> FleetCard {
                    Text(model.error ?: "Model information unavailable.", style = MaterialTheme.typography.bodySmall)
                    TextButton(onClick = viewModel::loadModel) { Text("Retry") }
                }
            }

            // ---------------------------------------------------------------- demo data
            SectionHeader("Demo data")
            FleetCard {
                Text(
                    if (gitHub) "The GitHub data never changes. Alerts you mark as read are remembered on this phone; reset clears them."
                    else "Services recorded from the app change the server's demo database and the AI re-scores those vehicles. " +
                        "Reset restores the original data (admin only).",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(10.dp))
                OutlinedButton(onClick = { confirmReset = true }, enabled = !resetting) {
                    if (resetting) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                    else {
                        Icon(Icons.Filled.Refresh, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(6.dp))
                        Text(if (gitHub) "Clear changes on this phone" else "Reset demo data")
                    }
                }
            }

            // ---------------------------------------------------------------- about
            SectionHeader("About")
            FleetCard {
                InfoRow("App version", BuildConfig.VERSION_NAME)
                HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                InfoRow("Data", "Simulated Pakistani fleet, 2023–2025")
                HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                InfoRow("Live tracking (GPS)", "Planned — needs GPS devices")
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { uri.openUri(BuildConfig.DASHBOARD_URL) }) { Text("Web dashboard") }
                    OutlinedButton(onClick = { uri.openUri(BuildConfig.REPO_URL) }) { Text("Source code") }
                }
            }
        }
    }

    if (confirmSignOut) {
        AlertDialog(
            onDismissRequest = { confirmSignOut = false },
            title = { Text("Sign out?") },
            text = { Text("You'll need your username and password to sign in again. Saved offline data is cleared.") },
            confirmButton = { Button(onClick = { confirmSignOut = false; viewModel.signOut() }) { Text("Sign out") } },
            dismissButton = { TextButton(onClick = { confirmSignOut = false }) { Text("Cancel") } },
        )
    }
    if (confirmReset) {
        AlertDialog(
            onDismissRequest = { confirmReset = false },
            title = { Text(if (gitHub) "Clear changes on this phone?" else "Reset demo data?") },
            text = {
                Text(if (gitHub) "Alerts you marked as read on this phone become unread again."
                else "All services recorded from the app are removed and every vehicle is re-scored by the AI model.")
            },
            confirmButton = { Button(onClick = { confirmReset = false; viewModel.resetDemo() }) { Text("Reset") } },
            dismissButton = { TextButton(onClick = { confirmReset = false }) { Text("Cancel") } },
        )
    }
}

@Composable
private fun ModelCard(info: ModelInfo) {
    val m = info.riskModel
    FleetCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(FleetIcons.Sparkle, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(8.dp))
            Text(m.name, style = MaterialTheme.typography.titleSmall)
        }
        Spacer(Modifier.height(6.dp))
        InfoRow("Predicts", m.target)
        InfoRow("Validation", "Time-based (test = 2025)")
        Spacer(Modifier.height(8.dp))
        Text("Test results", style = MaterialTheme.typography.labelLarge)
        Row(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
            listOf("Model", "ROC-AUC", "PR-AUC", "Recall").forEachIndexed { i, h ->
                Text(h, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.weight(if (i == 0) 1.6f else 1f))
            }
        }
        m.metrics.forEach { r ->
            Row(Modifier.fillMaxWidth().padding(vertical = 3.dp)) {
                Text(r.model.replace("Baseline: ", "Rule: "), style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1.6f))
                listOf(r.rocAuc, r.prAuc, r.recall).forEach { v ->
                    Text(v?.let { Format.decimal(it, 2) } ?: "–", style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f))
                }
            }
        }
        Spacer(Modifier.height(10.dp))
        Text("What drives the risk (mean |SHAP|)", style = MaterialTheme.typography.labelLarge)
        val max = info.explainability.maxOfOrNull { it.meanAbsShap }?.takeIf { it > 0 } ?: 1.0
        info.explainability.take(6).forEach { f ->
            Column(Modifier.padding(vertical = 4.dp)) {
                Text(f.feature.replaceFirstChar { it.uppercase() }, style = MaterialTheme.typography.bodySmall)
                Box(Modifier.fillMaxWidth().height(6.dp).clip(MaterialTheme.shapes.small).background(MaterialTheme.colorScheme.surfaceVariant)) {
                    Box(Modifier.fillMaxWidth((f.meanAbsShap / max).toFloat()).fillMaxHeight().background(Tone.BRAND.accent()))
                }
            }
        }
        Spacer(Modifier.height(10.dp))
        Text("Fuel anomaly detector", style = MaterialTheme.typography.labelLarge)
        Text(info.fuelAnomaly.rule, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        info.fuelAnomaly.metrics.forEach { a ->
            InfoRow(a.detector, "F1 ${a.f1?.let { Format.decimal(it, 2) } ?: "–"}")
        }
        Spacer(Modifier.height(8.dp))
        Text("Scores", style = MaterialTheme.typography.labelLarge)
        listOf(info.healthFormula, info.safetyFormula, info.performanceFormula).filter { it.isNotBlank() }.forEach {
            Text("• $it", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if (info.dataNote.isNotBlank()) {
            Spacer(Modifier.height(10.dp))
            Banner(info.dataNote, Tone.WARNING)
        }
    }
}
