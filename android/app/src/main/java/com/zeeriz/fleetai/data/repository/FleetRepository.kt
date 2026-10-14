package com.zeeriz.fleetai.data.repository

import com.zeeriz.fleetai.data.local.AppSettings
import com.zeeriz.fleetai.data.local.DataSource
import com.zeeriz.fleetai.data.local.ResponseCache
import com.zeeriz.fleetai.data.local.SettingsStore
import com.zeeriz.fleetai.data.remote.ApiProvider
import com.zeeriz.fleetai.data.remote.ApiResult
import com.zeeriz.fleetai.data.remote.FleetApi
import com.zeeriz.fleetai.data.remote.FleetJson
import com.zeeriz.fleetai.data.remote.toFailure
import com.zeeriz.fleetai.domain.model.Dashboard
import com.zeeriz.fleetai.domain.model.FuelAnomalies
import com.zeeriz.fleetai.domain.model.FuelCheckRequest
import com.zeeriz.fleetai.domain.model.FuelCheckResult
import com.zeeriz.fleetai.domain.model.FuelSummary
import com.zeeriz.fleetai.domain.model.DriverDetail
import com.zeeriz.fleetai.domain.model.DriverList
import com.zeeriz.fleetai.domain.model.TripPage
import com.zeeriz.fleetai.domain.model.AlertList
import com.zeeriz.fleetai.domain.model.Health
import com.zeeriz.fleetai.domain.model.LoginRequest
import com.zeeriz.fleetai.domain.model.ModelInfo
import com.zeeriz.fleetai.domain.model.ResetResult
import com.zeeriz.fleetai.domain.model.ReadResult
import com.zeeriz.fleetai.domain.model.MaintenancePage
import com.zeeriz.fleetai.domain.model.MaintenanceSummary
import com.zeeriz.fleetai.domain.model.ScheduleItem
import com.zeeriz.fleetai.domain.model.Prediction
import com.zeeriz.fleetai.domain.model.ServiceRecordRequest
import com.zeeriz.fleetai.domain.model.ServiceRecordResult
import com.zeeriz.fleetai.domain.model.VehicleDetail
import com.zeeriz.fleetai.domain.model.VehicleSummary
import kotlinx.serialization.builtins.ListSerializer
import com.zeeriz.fleetai.domain.model.User
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.serialization.KSerializer

/** Current session (server address + token), read by the HTTP client for every request. */
class Session {
    @Volatile
    var snapshot: AppSettings = AppSettings()
}

/**
 * Single entry point to the fleet data: the live FastAPI server or the read-only snapshot published on GitHub
 * (Profile > Data source). Successful responses are cached; when the source cannot be reached, the last cached
 * copy is returned and flagged `fromCache` so screens can show an "offline" banner.
 */
class FleetRepository(
    private val settings: SettingsStore,
    private val apiProvider: ApiProvider,
    private val gitHub: FleetApi,
    private val cache: ResponseCache,
    private val session: Session,
) {
    private val _unreadAlerts = MutableStateFlow(0)
    val unreadAlerts: StateFlow<Int> = _unreadAlerts.asStateFlow()

    @Volatile
    private var sessionLoaded = false

    private suspend fun currentSession(): AppSettings {
        if (!sessionLoaded) {
            session.snapshot = settings.settings.first()
            sessionLoaded = true
        }
        return session.snapshot
    }

    private suspend fun api(): FleetApi =
        currentSession().let { if (it.dataSource == DataSource.GITHUB) gitHub else apiProvider.api(it.serverUrl) }

    private suspend fun Throwable.asFailure(): ApiResult.Failure =
        currentSession().let { toFailure(it.serverUrl, fromGitHub = it.dataSource == DataSource.GITHUB) }

    /** Switches between the GitHub snapshot and the live server; cached data of the other source is dropped. */
    suspend fun setDataSource(source: DataSource) {
        if (currentSession().dataSource == source) return
        settings.setDataSource(source)
        cache.clear()
        session.snapshot = session.snapshot.copy(dataSource = source)
        _unreadAlerts.value = 0
    }

    suspend fun login(username: String, password: String, serverUrl: String): ApiResult<User> {
        val url = serverUrl.trim().trimEnd('/')
        settings.setServerUrl(url)
        session.snapshot = currentSession().copy(serverUrl = url)
        return try {
            val token = apiProvider.api(url).login(LoginRequest(username.trim(), password))
            settings.saveSession(token.accessToken, token.user.username, token.user.fullName)
            setDataSource(DataSource.SERVER)
            session.snapshot = session.snapshot.copy(
                token = token.accessToken, username = token.user.username, fullName = token.user.fullName,
            )
            ApiResult.Success(token.user)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) {
            val failure = e.toFailure(url)
            if (failure.kind == ApiResult.Kind.UNAUTHORIZED) ApiResult.Failure("Wrong username or password.", failure.kind)
            else failure
        }
    }

    suspend fun logout() {
        settings.clearSession()
        cache.clear()
        session.snapshot = currentSession().copy(token = null, fullName = null)
        _unreadAlerts.value = 0
    }

    suspend fun dashboard(): ApiResult<Dashboard> =
        fetch("dashboard", Dashboard.serializer()) { api().dashboard() }
            .also { if (it is ApiResult.Success) _unreadAlerts.value = it.data.unreadAlerts }

    suspend fun vehicles(): ApiResult<List<VehicleSummary>> =
        fetch("vehicles", ListSerializer(VehicleSummary.serializer())) { api().vehicles() }

    suspend fun vehicle(id: Int): ApiResult<VehicleDetail> =
        fetch("vehicle_$id", VehicleDetail.serializer()) { api().vehicle(id) }

    suspend fun maintenanceSummary(): ApiResult<MaintenanceSummary> =
        fetch("maintenance_summary", MaintenanceSummary.serializer()) { api().maintenanceSummary() }

    suspend fun maintenanceSchedule(status: String): ApiResult<List<ScheduleItem>> =
        fetch("schedule_$status", ListSerializer(ScheduleItem.serializer())) { api().maintenanceSchedule(status) }

    suspend fun maintenanceHistory(kind: String?, offset: Int, limit: Int = 50): ApiResult<MaintenancePage> =
        fetch("history_${kind ?: "all"}_$offset", MaintenancePage.serializer()) { api().maintenanceHistory(kind, limit, offset) }

    suspend fun fuelSummary(days: Int): ApiResult<FuelSummary> =
        fetch("fuel_summary_$days", FuelSummary.serializer()) { api().fuelSummary(days) }

    suspend fun fuelAnomalies(days: Int): ApiResult<FuelAnomalies> =
        fetch("fuel_anomalies_$days", FuelAnomalies.serializer()) { api().fuelAnomalies(days) }

    suspend fun fuelCheck(vehicleId: Int, distanceKm: Double, litres: Double): ApiResult<FuelCheckResult> =
        send { api().fuelCheck(FuelCheckRequest(vehicleId, distanceKm, litres)) }

    suspend fun drivers(): ApiResult<DriverList> = fetch("drivers", DriverList.serializer()) { api().drivers() }

    suspend fun driver(id: Int): ApiResult<DriverDetail> = fetch("driver_$id", DriverDetail.serializer()) { api().driver(id) }

    suspend fun trips(offset: Int, driverId: Int? = null): ApiResult<TripPage> =
        fetch("trips_${driverId ?: "all"}_$offset", TripPage.serializer()) { api().trips(driverId = driverId, offset = offset) }

    /** All alerts with this user's read-state; also refreshes the bottom-bar badge. */
    suspend fun alerts(): ApiResult<AlertList> =
        fetch("alerts", AlertList.serializer()) { api().alerts() }
            .also { if (it is ApiResult.Success && !it.fromCache) _unreadAlerts.value = it.data.unread }

    suspend fun markAlertRead(id: String): ApiResult<ReadResult> =
        send { api().markAlertRead(id) }.also { if (it is ApiResult.Success) _unreadAlerts.value = (_unreadAlerts.value - 1).coerceAtLeast(0) }

    suspend fun markAllAlertsRead(): ApiResult<ReadResult> =
        send { api().markAllAlertsRead() }.also { if (it is ApiResult.Success) _unreadAlerts.value = 0 }

    suspend fun modelInfo(): ApiResult<ModelInfo> = fetch("model_info", ModelInfo.serializer()) { api().modelInfo() }

    /** Live connectivity check (never cached). */
    suspend fun health(): ApiResult<Health> = send { api().health() }

    suspend fun resetDemo(): ApiResult<ResetResult> = send { api().resetDemo() }

    /** Writes are never served from the cache: they either reach the server or fail. */
    suspend fun predict(id: Int): ApiResult<Prediction> = send { api().predict(id) }

    suspend fun recordService(vehicleId: Int, service: String, notes: String? = null): ApiResult<ServiceRecordResult> =
        send { api().recordService(ServiceRecordRequest(vehicleId, service, notes = notes)) }

    private suspend fun <T> send(call: suspend () -> T): ApiResult<T> =
        try {
            ApiResult.Success(call())
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) {
            e.asFailure().also { if (it.kind == ApiResult.Kind.UNAUTHORIZED) logout() }
        }

    /** Calls the API, caches the result, falls back to the cache when offline, signs out on 401. */
    private suspend fun <T> fetch(name: String, serializer: KSerializer<T>, call: suspend () -> T): ApiResult<T> {
        val key = "${currentSession().dataSource.name.lowercase()}_$name"
        return try {
            val data = call()
            cache.put(key, FleetJson.encodeToString(serializer, data))
            ApiResult.Success(data)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) {
            val failure = e.asFailure()
            when (failure.kind) {
                ApiResult.Kind.UNAUTHORIZED -> {
                    logout()
                    failure
                }
                ApiResult.Kind.NETWORK, ApiResult.Kind.SERVER -> cache.get(key)?.let { (json, savedAt) ->
                    runCatching { ApiResult.Success(FleetJson.decodeFromString(serializer, json), fromCache = true, savedAt = savedAt) }
                        .getOrNull()
                } ?: failure
                else -> failure
            }
        }
    }
}
