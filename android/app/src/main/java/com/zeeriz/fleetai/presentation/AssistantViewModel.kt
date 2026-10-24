package com.zeeriz.fleetai.presentation

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.zeeriz.fleetai.data.remote.ApiResult
import com.zeeriz.fleetai.data.remote.ChatButton
import com.zeeriz.fleetai.data.remote.ChatProfile
import com.zeeriz.fleetai.data.repository.AssistantRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class ChatMessage(
    val id: Long,
    val fromUser: Boolean,
    val text: String,
    val buttons: List<ChatButton> = emptyList(),
    val failed: Boolean = false,
)

data class AssistantState(
    val messages: List<ChatMessage> = emptyList(),
    val sending: Boolean = false,
    val profile: ChatProfile = ChatProfile(),
    val configured: Boolean = true,
) {
    /** One-tap starters that match what the assistant understands for the current role. */
    val suggestions: List<String>
        get() = when (profile.role) {
            "driver" -> listOf("slot", "meri bookings", "meri driving kaisi hai?", "accident ho gaya")
            "manager" -> listOf("brief", "issues", "bookings", "budget 1 lakh", "subscribe")
            else -> listOf("driver LEA-22-2030", "manager")
        }
}

const val ASSISTANT_WELCOME = "👋 FleetLog AI — AI Fleet Log Assistant\n" +
    "Driver ho to: 'driver LEA-22-2030' likhein, phir masla, fuel, shift ya 'slot'. 🎤 se bol bhi sakte hain.\n" +
    "Manager ho to: 'manager' likhein; subah ki report: 'brief'.\n" +
    "Demo fleet (simulated); risk data 1 Jan 2026 tak."

class AssistantViewModel(private val repository: AssistantRepository) : ViewModel() {
    private var nextId = 0L
    private val _state = MutableStateFlow(
        AssistantState(messages = listOf(ChatMessage(nextId++, false, ASSISTANT_WELCOME)), configured = repository.isConfigured),
    )
    val state: StateFlow<AssistantState> = _state.asStateFlow()

    fun send(text: String) {
        val message = text.trim()
        if (message.isEmpty() || _state.value.sending) return
        _state.update { it.copy(messages = it.messages + ChatMessage(nextId++, true, message), sending = true) }
        viewModelScope.launch {
            val reply = when (val r = repository.send(message)) {
                is ApiResult.Success -> {
                    _state.update { it.copy(profile = r.data.profile) }
                    ChatMessage(nextId++, false, r.data.reply, r.data.buttons)
                }
                is ApiResult.Failure -> ChatMessage(nextId++, false, r.message, failed = true)
            }
            _state.update { it.copy(messages = it.messages + reply, sending = false) }
        }
    }

    /** Inline buttons (Approve, Call driver, ...) send their action text, exactly like typing it. */
    fun press(button: ChatButton) = send(button.action)

    fun startOver() {
        viewModelScope.launch {
            repository.reset()
            _state.update { AssistantState(messages = listOf(ChatMessage(nextId++, false, ASSISTANT_WELCOME)), configured = it.configured) }
        }
    }

    companion object {
        val Factory = viewModelFactory { initializer { AssistantViewModel(container.assistant) } }
    }
}
