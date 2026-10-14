package com.zeeriz.fleetai.data.remote

import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import retrofit2.HttpException
import java.io.IOException
import java.net.SocketTimeoutException

/** Outcome of a backend call, with a message that can be shown to the user as-is. */
sealed interface ApiResult<out T> {
    data class Success<T>(val data: T, val fromCache: Boolean = false, val savedAt: Long? = null) : ApiResult<T>
    data class Failure(val message: String, val kind: Kind) : ApiResult<Nothing>

    enum class Kind { NETWORK, UNAUTHORIZED, NOT_FOUND, SERVER, INVALID }
}

/**
 * Turns exceptions from Retrofit/OkHttp into readable failures (never leaks stack traces to the UI).
 * [fromGitHub] = the app is reading the published snapshot, so network advice is about internet, not the laptop.
 */
fun Throwable.toFailure(serverUrl: String, fromGitHub: Boolean = false): ApiResult.Failure = when {
    this is LiveServerRequiredException -> ApiResult.Failure(message.orEmpty(), ApiResult.Kind.INVALID)
    fromGitHub -> when (this) {
        is HttpException -> if (code() == 404) ApiResult.Failure("This item is not in the published data.", ApiResult.Kind.NOT_FOUND)
        else ApiResult.Failure("GitHub returned an error (${code()}). Try again in a minute.", ApiResult.Kind.SERVER)
        is IOException -> ApiResult.Failure("Can't load the fleet data. Check your internet connection and pull down to retry.", ApiResult.Kind.NETWORK)
        is SerializationException -> ApiResult.Failure("The published data could not be read.", ApiResult.Kind.SERVER)
        is IllegalArgumentException -> ApiResult.Failure(message ?: "Some values are not valid.", ApiResult.Kind.INVALID)
        else -> ApiResult.Failure("The published data could not be read.", ApiResult.Kind.SERVER)
    }
    else -> serverFailure(serverUrl)
}

private fun Throwable.serverFailure(serverUrl: String): ApiResult.Failure = when (this) {
    is HttpException -> {
        val detail = errorDetail(this)
        when (code()) {
            401 -> ApiResult.Failure(detail ?: "Please sign in again.", ApiResult.Kind.UNAUTHORIZED)
            404 -> ApiResult.Failure(detail ?: "Not found.", ApiResult.Kind.NOT_FOUND)
            422 -> ApiResult.Failure(detail ?: "Some values are not valid.", ApiResult.Kind.INVALID)
            else -> ApiResult.Failure(detail ?: "Server error (${code()}). Try again.", ApiResult.Kind.SERVER)
        }
    }
    is SocketTimeoutException -> ApiResult.Failure("The server at $serverUrl is taking too long to answer.", ApiResult.Kind.NETWORK)
    is IOException -> ApiResult.Failure(
        "Can't reach the server at $serverUrl. Make sure the FastAPI server is running and the address is right (Profile > Server).",
        ApiResult.Kind.NETWORK,
    )
    else -> ApiResult.Failure("Unexpected response from the server.", ApiResult.Kind.SERVER)
}

/** FastAPI errors look like {"detail": "text"} or {"detail": [{"msg": "...", "loc": [...]}]}. */
private fun errorDetail(e: HttpException): String? = runCatching {
    val body = e.response()?.errorBody()?.string().orEmpty()
    when (val detail = FleetJson.parseToJsonElement(body).jsonObject["detail"]) {
        is JsonPrimitive -> detail.content
        is JsonArray -> detail.joinToString("; ") { (it as? JsonObject)?.get("msg")?.jsonPrimitive?.content.orEmpty() }
        else -> null
    }
}.getOrNull()?.takeIf { it.isNotBlank() }
