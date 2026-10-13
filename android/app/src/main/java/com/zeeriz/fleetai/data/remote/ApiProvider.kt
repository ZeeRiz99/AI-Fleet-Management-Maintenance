package com.zeeriz.fleetai.data.remote

import com.zeeriz.fleetai.BuildConfig
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNamingStrategy
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.util.concurrent.TimeUnit

/** Shared JSON settings: snake_case API keys <-> camelCase Kotlin properties, tolerant of new fields. */
@OptIn(ExperimentalSerializationApi::class)
val FleetJson = Json {
    ignoreUnknownKeys = true
    explicitNulls = false
    coerceInputValues = true
    namingStrategy = JsonNamingStrategy.SnakeCase
}

/**
 * Builds the Retrofit client for the current server address (changeable in Profile) and attaches the
 * session token to every request. The client is rebuilt only when the address changes.
 */
class ApiProvider(private val tokenProvider: () -> String?) {

    @Volatile
    private var cached: Pair<String, FleetApi>? = null

    private val http: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .connectTimeout(8, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)   // AI re-scoring can take a few seconds
            .addInterceptor { chain ->
                val token = tokenProvider()
                val request = if (token.isNullOrBlank()) chain.request()
                else chain.request().newBuilder().header("Authorization", "Bearer $token").build()
                chain.proceed(request)
            }
            .apply {
                if (BuildConfig.DEBUG) {
                    addInterceptor(HttpLoggingInterceptor().setLevel(HttpLoggingInterceptor.Level.BASIC))
                }
            }
            .build()
    }

    fun api(baseUrl: String): FleetApi {
        val url = baseUrl.trim().trimEnd('/') + "/"
        cached?.let { (cachedUrl, api) -> if (cachedUrl == url) return api }
        val api = Retrofit.Builder()
            .baseUrl(url)
            .client(http)
            .addConverterFactory(FleetJson.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(FleetApi::class.java)
        cached = url to api
        return api
    }
}
