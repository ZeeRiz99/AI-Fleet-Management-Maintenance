package com.zeeriz.fleetai.data.repository

import com.zeeriz.fleetai.data.local.SettingsStore
import com.zeeriz.fleetai.data.remote.ApiResult
import com.zeeriz.fleetai.data.remote.AssistantApi
import com.zeeriz.fleetai.data.remote.ChatRequest
import com.zeeriz.fleetai.data.remote.ChatResponse
import kotlinx.coroutines.CancellationException
import retrofit2.HttpException
import java.io.IOException
import java.net.SocketTimeoutException

/**
 * Talks to FleetLog AI. Each install gets a random session id (kept in DataStore): the assistant remembers the
 * user's role and vehicle per session, like a Telegram chat.
 */
class AssistantRepository(
    private val settings: SettingsStore,
    private val baseUrl: String,
    private val appKey: String,
    private val api: AssistantApi? = baseUrl.takeIf { it.isNotBlank() }?.let { AssistantApi.create(it) },
) {
    val isConfigured: Boolean get() = api != null && appKey.isNotBlank()

    suspend fun send(text: String): ApiResult<ChatResponse> {
        val client = api
        if (client == null || appKey.isBlank()) {
            return ApiResult.Failure("FleetLog AI is not set up in this build (no server address or app key).",
                ApiResult.Kind.INVALID)
        }
        return try {
            ApiResult.Success(client.chat(appKey, ChatRequest(settings.assistantSession(), text.trim())))
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) {
            e.toAssistantFailure()
        }
    }

    /** Starting over: a new session id means a fresh role, vehicle and history on the server. */
    suspend fun reset() = settings.resetAssistantSession()
}

internal fun Throwable.toAssistantFailure(): ApiResult.Failure = when (this) {
    is HttpException -> when (code()) {
        403 -> ApiResult.Failure("This app version is not allowed to use FleetLog AI. Update the app.", ApiResult.Kind.UNAUTHORIZED)
        422 -> ApiResult.Failure("The message could not be sent. Try a shorter one.", ApiResult.Kind.INVALID)
        else -> ApiResult.Failure("FleetLog AI had a problem (${code()}). Try again in a minute.", ApiResult.Kind.SERVER)
    }
    is SocketTimeoutException -> ApiResult.Failure("FleetLog AI is taking too long. Try again.", ApiResult.Kind.NETWORK)
    is IOException -> ApiResult.Failure("No connection to FleetLog AI. Check the internet and try again.", ApiResult.Kind.NETWORK)
    else -> ApiResult.Failure("Unexpected answer from FleetLog AI.", ApiResult.Kind.SERVER)
}
