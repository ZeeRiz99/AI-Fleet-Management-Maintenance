package com.zeeriz.fleetai

import com.zeeriz.fleetai.data.remote.ApiResult
import com.zeeriz.fleetai.data.remote.ChatRequest
import com.zeeriz.fleetai.data.remote.ChatResponse
import com.zeeriz.fleetai.data.remote.FleetJson
import com.zeeriz.fleetai.data.repository.toAssistantFailure
import com.zeeriz.fleetai.presentation.AssistantState
import com.zeeriz.fleetai.data.remote.ChatProfile
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException

/** FleetLog AI chat: a real /api/chat response (ops/web.py, captured to resources/api/chat.json) must parse. */
class AssistantContractTest {
    private fun fixture(name: String): String =
        requireNotNull(javaClass.classLoader?.getResource("api/$name")) { "missing fixture $name" }.readText()

    @Test
    fun chatResponseParses() {
        val r = FleetJson.decodeFromString(ChatResponse.serializer(), fixture("chat.json"))
        assertTrue(r.reply.startsWith("⚠️ Hifazat pehle"))
        assertEquals("driver", r.profile.role)
        assertEquals("LEA-22-2030", r.profile.registration)
        assertEquals(listOf("call ISS-1001", "resolve ISS-1001"), r.buttons.map { it.action })
    }

    @Test
    fun chatRequestUsesTheServerFieldNames() {
        val json = FleetJson.encodeToString(ChatRequest.serializer(), ChatRequest("abcd-1234", "slot"))
        assertEquals("""{"session":"abcd-1234","text":"slot"}""", json)
    }

    @Test
    fun minimalResponseStillParses() {
        val r = FleetJson.decodeFromString(ChatResponse.serializer(), """{"reply":"Salam"}""")
        assertEquals("Salam", r.reply)
        assertTrue(r.buttons.isEmpty())
    }

    @Test
    fun suggestionsFollowTheRole() {
        assertEquals("driver LEA-22-2030", AssistantState().suggestions.first())
        assertTrue("slot" in AssistantState(profile = ChatProfile(role = "driver")).suggestions)
        assertTrue("brief" in AssistantState(profile = ChatProfile(role = "manager")).suggestions)
    }

    @Test
    fun networkErrorsReadWell() {
        val f = IOException("boom").toAssistantFailure()
        assertEquals(ApiResult.Kind.NETWORK, f.kind)
        assertTrue(f.message.contains("internet"))
    }
}
