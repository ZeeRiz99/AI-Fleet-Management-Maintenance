package com.zeeriz.fleetai.data.remote

import com.zeeriz.fleetai.data.local.AlertReadStore
import com.zeeriz.fleetai.domain.FuelBaselines
import com.zeeriz.fleetai.domain.FuelRule
import com.zeeriz.fleetai.domain.model.Alert
import com.zeeriz.fleetai.domain.model.AlertList
import com.zeeriz.fleetai.domain.model.Dashboard
import com.zeeriz.fleetai.domain.model.DriverDetail
import com.zeeriz.fleetai.domain.model.DriverList
import com.zeeriz.fleetai.domain.model.FuelAnomalies
import com.zeeriz.fleetai.domain.model.FuelCheckRequest
import com.zeeriz.fleetai.domain.model.FuelCheckResult
import com.zeeriz.fleetai.domain.model.FuelSummary
import com.zeeriz.fleetai.domain.model.Health
import com.zeeriz.fleetai.domain.model.LoginRequest
import com.zeeriz.fleetai.domain.model.MaintenancePage
import com.zeeriz.fleetai.domain.model.MaintenanceSummary
import com.zeeriz.fleetai.domain.model.ModelInfo
import com.zeeriz.fleetai.domain.model.Prediction
import com.zeeriz.fleetai.domain.model.ReadResult
import com.zeeriz.fleetai.domain.model.ResetResult
import com.zeeriz.fleetai.domain.model.ScheduleItem
import com.zeeriz.fleetai.domain.model.ServiceRecordRequest
import com.zeeriz.fleetai.domain.model.ServiceRecordResult
import com.zeeriz.fleetai.domain.model.TokenResponse
import com.zeeriz.fleetai.domain.model.TripPage
import com.zeeriz.fleetai.domain.model.User
import com.zeeriz.fleetai.domain.model.VehicleDetail
import com.zeeriz.fleetai.domain.model.VehicleSummary
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.KSerializer
import kotlinx.serialization.builtins.ListSerializer
import okhttp3.OkHttpClient
import okhttp3.ResponseBody
import retrofit2.Retrofit
import retrofit2.http.GET
import retrofit2.http.Url
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit

/** Thrown for actions that need the live AI server (they are never faked in GitHub mode). */
class LiveServerRequiredException(action: String) :
    Exception("$action needs the live AI server. Switch the data source to \"Live server\" in Profile.")

/** Raw JSON files of the published snapshot. */
interface StaticFiles {
    @GET
    suspend fun get(@Url path: String): ResponseBody
}

/**
 * [FleetApi] backed by the read-only API snapshot in the GitHub repo (static-api/v1, made by api/export_static.py).
 * Every response is a real output of the backend and its model; this class only serves the files, applies paging
 * and filters the server would apply, keeps alert read-marks on the phone, and runs the fuel rule locally.
 * Re-scoring a vehicle needs the trained model and database, so those calls ask for the live server instead.
 */
class GitHubFleetApi(private val files: StaticFiles, private val reads: AlertReadStore) : FleetApi {

    /** Larger files that back paged lists are downloaded once per app session. */
    private val memo = ConcurrentHashMap<String, Any>()

    private suspend fun <T> load(path: String, serializer: KSerializer<T>): T {
        val body = files.get(path)
        return withContext(Dispatchers.IO) { body.use { FleetJson.decodeFromString(serializer, it.string()) } }
    }

    @Suppress("UNCHECKED_CAST")
    private suspend fun <T : Any> memoized(path: String, serializer: KSerializer<T>): T =
        (memo[path] as T?) ?: load(path, serializer).also { memo[path] = it }

    private fun Alert.withLocalRead(readIds: Set<String>) = if (!read && id in readIds) copy(read = true) else this

    override suspend fun health(): Health = load("health.json", Health.serializer())

    override suspend fun login(body: LoginRequest): TokenResponse = throw LiveServerRequiredException("Signing in")

    override suspend fun me(): User = User(username = "demo", fullName = "Demo viewer", role = "viewer")

    override suspend fun dashboard(): Dashboard {
        val dashboard = load("dashboard.json", Dashboard.serializer())
        val readIds = reads.ids()
        if (readIds.isEmpty()) return dashboard
        return dashboard.copy(
            unreadAlerts = alerts().unread,
            recentAlerts = dashboard.recentAlerts.map { it.withLocalRead(readIds) },
        )
    }

    override suspend fun vehicles(): List<VehicleSummary> = load("vehicles.json", ListSerializer(VehicleSummary.serializer()))

    override suspend fun vehicle(id: Int): VehicleDetail = load("vehicles/$id.json", VehicleDetail.serializer())

    override suspend fun maintenanceSummary(): MaintenanceSummary = load("maintenance/summary.json", MaintenanceSummary.serializer())

    override suspend fun maintenanceSchedule(status: String, limit: Int): List<ScheduleItem> =
        load("maintenance/schedule_$status.json", ListSerializer(ScheduleItem.serializer())).take(limit)

    override suspend fun maintenanceHistory(kind: String?, limit: Int, offset: Int): MaintenancePage {
        val all = memoized("maintenance/history.json", MaintenancePage.serializer()).items
        val items = if (kind == null) all else all.filter { it.kind.equals(kind, ignoreCase = true) }
        return MaintenancePage(total = items.size, items = items.drop(offset).take(limit))
    }

    override suspend fun fuelSummary(days: Int): FuelSummary = load("fuel/summary_$days.json", FuelSummary.serializer())

    override suspend fun fuelAnomalies(days: Int, limit: Int): FuelAnomalies =
        load("fuel/anomalies_$days.json", FuelAnomalies.serializer()).let { it.copy(items = it.items.take(limit)) }

    override suspend fun fuelCheck(body: FuelCheckRequest): FuelCheckResult {
        val baselines = memoized("fuel/baselines.json", FuelBaselines.serializer())
        val vehicle = baselines.vehicles[body.vehicleId.toString()]
            ?: throw IllegalArgumentException("Vehicle ${body.vehicleId} is not in the data.")
        return FuelRule.check(body.vehicleId, vehicle, baselines.threshold, body.distanceKm, body.fuelLitres)
    }

    override suspend fun drivers(days: Int): DriverList = load("drivers.json", DriverList.serializer())

    override suspend fun driver(id: Int, days: Int): DriverDetail = load("drivers/$id.json", DriverDetail.serializer())

    override suspend fun trips(vehicleId: Int?, driverId: Int?, limit: Int, offset: Int): TripPage {
        val page = memoized("trips.json", TripPage.serializer())
        val items = page.items.filter { (vehicleId == null || it.vehicleId == vehicleId) && (driverId == null || it.driverId == driverId) }
        return page.copy(total = items.size, items = items.drop(offset).take(limit))
    }

    override suspend fun alerts(): AlertList {
        val list = memoized("alerts.json", AlertList.serializer())
        val readIds = reads.ids()
        val items = list.items.map { it.withLocalRead(readIds) }
        return list.copy(items = items, unread = items.count { !it.read })
    }

    override suspend fun markAlertRead(id: String): ReadResult {
        reads.add(listOf(id))
        return ReadResult(id = id, read = true, marked = 1)
    }

    override suspend fun markAllAlertsRead(): ReadResult {
        val unread = alerts().items.filter { !it.read }.map { it.id }
        reads.add(unread)
        return ReadResult(read = true, marked = unread.size)
    }

    override suspend fun modelInfo(): ModelInfo = load("ai/model.json", ModelInfo.serializer())

    /** Clears what this phone changed (alert read-marks) and re-downloads the snapshot on next use. */
    override suspend fun resetDemo(): ResetResult {
        reads.clear()
        memo.clear()
        return ResetResult(status = "reset", vehicles = health().vehicles)
    }

    override suspend fun predict(id: Int): Prediction = throw LiveServerRequiredException("Re-running the AI model")

    override suspend fun recordService(body: ServiceRecordRequest): ServiceRecordResult =
        throw LiveServerRequiredException("Recording a service")

    companion object {
        fun create(baseUrl: String, reads: AlertReadStore): GitHubFleetApi {
            val http = OkHttpClient.Builder()          // no auth header: never send a server token to GitHub
                .connectTimeout(10, TimeUnit.SECONDS)
                .readTimeout(30, TimeUnit.SECONDS)
                .build()
            val files = Retrofit.Builder()
                .baseUrl(baseUrl.trimEnd('/') + "/")
                .client(http)
                .build()
                .create(StaticFiles::class.java)
            return GitHubFleetApi(files, reads)
        }
    }
}
