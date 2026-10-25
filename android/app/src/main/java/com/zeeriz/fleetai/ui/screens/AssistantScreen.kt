package com.zeeriz.fleetai.ui.screens

import android.app.Activity
import android.content.Intent
import android.speech.RecognizerIntent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SuggestionChip
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.zeeriz.fleetai.data.remote.ChatButton
import com.zeeriz.fleetai.presentation.AssistantViewModel
import com.zeeriz.fleetai.presentation.ChatMessage
import com.zeeriz.fleetai.ui.components.FleetIcons
import com.zeeriz.fleetai.ui.components.FleetScaffold
import kotlinx.coroutines.launch

/** Speech-to-text through the phone's own recogniser; Latin-script Indian English output reads as Roman Urdu. */
private fun speechIntent() = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
    .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
    .putExtra(RecognizerIntent.EXTRA_LANGUAGE, "en-IN")
    .putExtra(RecognizerIntent.EXTRA_PROMPT, "Bolein: masla, fuel, slot…")

@Composable
fun AssistantScreen(onBack: () -> Unit, viewModel: AssistantViewModel = viewModel(factory = AssistantViewModel.Factory)) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var draft by rememberSaveable { mutableStateOf("") }
    val listState = rememberLazyListState()
    val snackbar = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    // Some phones (e.g. without Google speech services) have no recogniser: then the mic is hidden and typing works.
    val canListen = remember { speechIntent().resolveActivity(context.packageManager) != null }
    val listen = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val heard = result.data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull()
        if (result.resultCode == Activity.RESULT_OK && !heard.isNullOrBlank()) viewModel.send(heard)
        else if (result.resultCode == Activity.RESULT_OK) scope.launch { snackbar.showSnackbar("Awaaz samajh nahi aayi, dobara bolein") }
    }

    LaunchedEffect(state.messages.size, state.sending) {
        val last = state.messages.size + (if (state.sending) 1 else 0) - 1
        if (last >= 0) listState.animateScrollToItem(last)
    }

    FleetScaffold(
        title = "Ask FleetLog AI",
        subtitle = when (state.profile.role) {
            "driver" -> "Driver · ${state.profile.registration.orEmpty()}"
            "manager" -> "Manager"
            else -> "AI Fleet Log Assistant"
        },
        onBack = onBack,
        snackbarHostState = snackbar,
        actions = { IconButton(onClick = viewModel::startOver) { Icon(Icons.Filled.Refresh, "Start over") } },
    ) { padding ->
        Column(Modifier.padding(padding).fillMaxSize().imePadding()) {
            if (!state.configured) {
                Surface(color = MaterialTheme.colorScheme.errorContainer, modifier = Modifier.fillMaxWidth()) {
                    Text(
                        "FleetLog AI is not configured in this build.",
                        Modifier.padding(12.dp),
                        color = MaterialTheme.colorScheme.onErrorContainer,
                    )
                }
            }
            LazyColumn(
                state = listState,
                modifier = Modifier.weight(1f).fillMaxWidth(),
                contentPadding = PaddingValues(12.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(state.messages, key = { it.id }) { message ->
                    MessageBubble(message, enabled = !state.sending, onButton = viewModel::press)
                }
                if (state.sending) item { ThinkingRow() }
            }
            Row(
                Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 12.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                state.suggestions.forEach { s ->
                    SuggestionChip(
                        onClick = { viewModel.send(s) },
                        label = { Text(s) },
                        enabled = !state.sending,
                        modifier = Modifier.semantics { contentDescription = s },
                    )
                }
            }
            Row(
                Modifier.fillMaxWidth().padding(12.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                OutlinedTextField(
                    value = draft,
                    onValueChange = { draft = it },
                    modifier = Modifier.weight(1f),
                    placeholder = { Text("Likhein… (jaise: brake se awaaz)") },
                    maxLines = 4,
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                    keyboardActions = KeyboardActions(onSend = { viewModel.send(draft); draft = "" }),
                )
                if (canListen) {
                    IconButton(onClick = { listen.launch(speechIntent()) }, enabled = !state.sending) {
                        Icon(FleetIcons.Mic, contentDescription = "Speak")
                    }
                }
                FilledIconButton(
                    onClick = { viewModel.send(draft); draft = "" },
                    enabled = draft.isNotBlank() && !state.sending,
                ) { Icon(Icons.AutoMirrored.Filled.Send, contentDescription = "Send") }
            }
        }
    }
}

@Composable
private fun MessageBubble(message: ChatMessage, enabled: Boolean, onButton: (ChatButton) -> Unit) {
    val colors = MaterialTheme.colorScheme
    val (background, foreground) = when {
        message.fromUser -> colors.primary to colors.onPrimary
        message.failed -> colors.errorContainer to colors.onErrorContainer
        else -> colors.surface to colors.onSurface
    }
    Box(Modifier.fillMaxWidth(), contentAlignment = if (message.fromUser) Alignment.CenterEnd else Alignment.CenterStart) {
        Column(horizontalAlignment = if (message.fromUser) Alignment.End else Alignment.Start) {
            Surface(
                color = background,
                shape = RoundedCornerShape(16.dp, 16.dp, if (message.fromUser) 4.dp else 16.dp, if (message.fromUser) 16.dp else 4.dp),
                tonalElevation = if (message.fromUser) 0.dp else 1.dp,
                modifier = Modifier.widthIn(max = 320.dp),
            ) {
                Text(message.text, Modifier.padding(horizontal = 12.dp, vertical = 8.dp), color = foreground,
                    style = MaterialTheme.typography.bodyMedium)
            }
            if (message.buttons.isNotEmpty()) {
                Row(
                    Modifier.padding(top = 4.dp).horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    message.buttons.forEach { b ->
                        OutlinedButton(
                            onClick = { onButton(b) },
                            enabled = enabled,
                            modifier = Modifier.semantics { contentDescription = b.text },
                        ) { Text(b.text) }
                    }
                }
            }
        }
    }
}

@Composable
private fun ThinkingRow() {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
        Text("FleetLog AI soch raha hai…", style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
