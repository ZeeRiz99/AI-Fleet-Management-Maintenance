package com.zeeriz.fleetai.data.remote

import kotlinx.serialization.Serializable
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import retrofit2.http.Body
import retrofit2.http.Header
import retrofit2.http.POST
import java.util.concurrent.TimeUnit

/** FleetLog AI chat (ops/web.py on Vercel): the same assistant drivers and managers use on Telegram. */
interface AssistantApi {
    @POST("api/chat")
    suspend fun chat(@Header("X-App-Key") appKey: String, @Body body: ChatRequest): ChatResponse

    companion object {
        fun create(baseUrl: String): AssistantApi = Retrofit.Builder()
            .baseUrl(baseUrl.trim().trimEnd('/') + "/")
            .client(
                OkHttpClient.Builder()
                    .connectTimeout(10, TimeUnit.SECONDS)
                    .readTimeout(70, TimeUnit.SECONDS)   // the AI may try two models and run several tools
                    .build(),
            )
            .addConverterFactory(FleetJson.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(AssistantApi::class.java)
    }
}

@Serializable
data class ChatRequest(val session: String, val text: String)

@Serializable
data class ChatButton(val text: String, val action: String)

@Serializable
data class ChatProfile(val role: String? = null, val registration: String? = null)

@Serializable
data class ChatResponse(
    val reply: String,
    val mode: String = "",
    val buttons: List<ChatButton> = emptyList(),
    val profile: ChatProfile = ChatProfile(),
)
