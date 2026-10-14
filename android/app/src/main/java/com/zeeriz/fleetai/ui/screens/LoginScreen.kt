package com.zeeriz.fleetai.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.zeeriz.fleetai.BuildConfig
import com.zeeriz.fleetai.presentation.LoginViewModel
import com.zeeriz.fleetai.ui.components.Banner
import com.zeeriz.fleetai.ui.components.FleetCard
import com.zeeriz.fleetai.ui.components.FleetIcons
import com.zeeriz.fleetai.ui.theme.Tone

@Composable
fun LoginScreen(viewModel: LoginViewModel = viewModel(factory = LoginViewModel.Factory)) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var showPassword by rememberSaveable { mutableStateOf(false) }
    var showServer by rememberSaveable { mutableStateOf(false) }

    Column(
        Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState())
            .imePadding(),
    ) {
        // Brand header
        Column(
            Modifier
                .fillMaxWidth()
                .background(Brush.linearGradient(listOf(Color(0xFF0B1220), Color(0xFF1E3A8A), Color(0xFF2563EB))))
                .statusBarsPadding()
                .padding(horizontal = 24.dp, vertical = 36.dp),
        ) {
            Box(
                Modifier.size(56.dp).clip(MaterialTheme.shapes.large).background(Color.White.copy(alpha = 0.14f)),
                contentAlignment = Alignment.Center,
            ) { Icon(FleetIcons.Truck, contentDescription = null, tint = Color.White, modifier = Modifier.size(30.dp)) }
            Spacer(Modifier.height(18.dp))
            Text("FleetAI", style = MaterialTheme.typography.headlineMedium, color = Color.White)
            Text(
                "Fleet management & predictive maintenance",
                style = MaterialTheme.typography.bodyMedium,
                color = Color(0xFFCBD5E1),
            )
        }

        Column(
            Modifier.fillMaxWidth().padding(20.dp).widthIn(max = 520.dp).align(Alignment.CenterHorizontally),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Column {
                Text("Sign in", style = MaterialTheme.typography.titleLarge)
                Text("to the live AI server (record services, re-run the model)", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            FleetCard {
                OutlinedTextField(
                    value = state.username,
                    onValueChange = viewModel::onUsername,
                    label = { Text("Username") },
                    leadingIcon = { Icon(Icons.Filled.Person, contentDescription = null) },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next),
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(
                    value = state.password,
                    onValueChange = viewModel::onPassword,
                    label = { Text("Password") },
                    leadingIcon = { Icon(Icons.Filled.Lock, contentDescription = null) },
                    trailingIcon = {
                        TextButton(onClick = { showPassword = !showPassword }) { Text(if (showPassword) "Hide" else "Show") }
                    },
                    singleLine = true,
                    visualTransformation = if (showPassword) VisualTransformation.None else PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Done),
                    keyboardActions = KeyboardActions(onDone = { viewModel.signIn() }),
                    modifier = Modifier.fillMaxWidth(),
                )

                AnimatedVisibility(visible = showServer) {
                    OutlinedTextField(
                        value = state.serverUrl,
                        onValueChange = viewModel::onServerUrl,
                        label = { Text("Server address") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                        supportingText = { Text("Emulator: http://10.0.2.2:8000 · Phone: http://<laptop-ip>:8000") },
                        modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
                    )
                }

                state.error?.let {
                    Spacer(Modifier.height(12.dp))
                    Banner(it, Tone.CRITICAL)
                }

                Spacer(Modifier.height(16.dp))
                Button(onClick = viewModel::signIn, enabled = state.canSubmit, modifier = Modifier.fillMaxWidth().height(48.dp)) {
                    if (state.loading) {
                        CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp, color = MaterialTheme.colorScheme.onPrimary)
                    } else {
                        Text("Sign in")
                    }
                }
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center) {
                    TextButton(onClick = { showServer = !showServer }) {
                        Icon(Icons.Filled.Settings, contentDescription = null, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.size(6.dp))
                        Text(if (showServer) "Hide server settings" else "Server settings")
                    }
                }
            }
            OutlinedButton(onClick = viewModel::useGitHubData, modifier = Modifier.fillMaxWidth().height(48.dp)) {
                Text("Explore demo data (no server needed)")
            }
            Text(
                "Opens the published fleet data and AI results from GitHub: no account or laptop server required.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (BuildConfig.DEBUG) {
                Text(
                    "Local demo account: admin / fleet123 (set FLEET_ADMIN_PASSWORD on the server for real use).",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}
