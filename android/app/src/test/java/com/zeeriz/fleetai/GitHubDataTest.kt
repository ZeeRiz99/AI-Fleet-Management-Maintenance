package com.zeeriz.fleetai

import com.zeeriz.fleetai.data.local.AlertReadStore
import com.zeeriz.fleetai.data.remote.FleetJson
import com.zeeriz.fleetai.data.remote.GitHubFleetApi
import com.zeeriz.fleetai.data.remote.LiveServerRequiredException
import com.zeeriz.fleetai.data.remote.StaticFiles
import com.zeeriz.fleetai.domain.FuelBaselines
import com.zeeriz.fleetai.domain.FuelRule
import com.zeeriz.fleetai.domain.model.FuelCheckRequest
import com.zeeriz.fleetai.domain.model.FuelCheckResult
import com.zeeriz.fleetai.domain.model.ServiceRecordRequest
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import okhttp3.ResponseBody
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.File
import java.io.FileNotFoundException

/**
 * The GitHub data source: the published snapshot (../../static-api/v1, made by api/export_static.py) must decode
 * with the app's models, paging/filters must behave like the server, and the on-phone fuel rule must give exactly
 * the backend's answer.
 */
class GitHubDataTest {
    private fun fixture(name: String): String =
        requireNotNull(javaClass.classLoader?.getResource("api/$name")) { "missing fixture $name" }.readText()

    /** Unit tests run with the module directory (android/app) as working directory. */
    private val snapshot = File("../../static-api/v1").also { require(it.isDirectory) { "run api/export_static.py first" } }

    private class MemoryReads : AlertReadStore {
        val set = mutableSetOf<String>()
        override fun ids() = set.toSet()
        override fun add(ids: Collection<String>) { set += ids }
        override fun clear() = set.clear()
    }

    private val reads = MemoryReads()
    private val api = GitHubFleetApi(
        files = object : StaticFiles {
            override suspend fun get(path: String): ResponseBody =
                File(snapshot, path).takeIf { it.isFile }?.readText()?.toResponseBody() ?: throw FileNotFoundException(path)
        },
        reads = reads,
    )

    @Test
    fun fuelRuleMatchesTheBackend() {
        val baselines = FleetJson.decodeFromString(FuelBaselines.serializer(), fixture("fuel_baselines.json"))
        val cases = FleetJson.parseToJsonElement(fixture("fuel_checks.json")).jsonArray
        assertTrue(cases.size >= 4)
        cases.forEach { case ->
            val request = FleetJson.decodeFromJsonElement(FuelCheckRequest.serializer(), case.jsonObject.getValue("request"))
            val expected = FleetJson.decodeFromJsonElement(FuelCheckResult.serializer(), case.jsonObject.getValue("result"))
            val actual = FuelRule.check(request.vehicleId, baselines.vehicles.getValue(request.vehicleId.toString()),
                baselines.threshold, request.distanceKm, request.fuelLitres)
            assertEquals("vehicle ${request.vehicleId}", expected, actual)
        }
    }

    @Test
    fun everyScreenLoadsFromTheSnapshot() = runBlocking {
        val vehicles = api.vehicles()
        assertEquals(58, vehicles.size)
        vehicles.forEach { assertEquals(it.id, api.vehicle(it.id).id) }
        assertEquals(58, api.dashboard().fleet.totalVehicles)
        assertEquals(58, api.health().vehicles)
        assertTrue(api.maintenanceSummary().overdue > 0)
        listOf("overdue", "due_soon").forEach { assertTrue(api.maintenanceSchedule(it, 600).isNotEmpty()) }
        listOf(7, 30, 90, 365).forEach { days ->
            assertTrue(api.fuelSummary(days).totals.trips > 0)
            assertEquals(days, api.fuelAnomalies(days, 100).days)
        }
        val drivers = api.drivers(180).items
        assertEquals(24, drivers.size)
        drivers.forEach { assertEquals(it.id, api.driver(it.id, 180).id) }
        assertTrue(api.modelInfo().riskModel.metrics.isNotEmpty())
    }

    @Test
    fun pagingAndFiltersBehaveLikeTheServer() = runBlocking {
        val all = api.maintenanceHistory(null, 50, 0)
        val preventive = api.maintenanceHistory("Preventive", 50, 0)
        val breakdown = api.maintenanceHistory("Breakdown", 50, 0)
        assertEquals(all.total, preventive.total + breakdown.total)
        assertEquals(50, all.items.size)
        assertTrue(breakdown.items.all { it.kind == "Breakdown" })
        val lastPage = api.maintenanceHistory(null, 50, all.total - 10)
        assertEquals(10, lastPage.items.size)

        val trips = api.trips(null, null, 30, 0)
        assertEquals(30, trips.items.size)
        val driverId = trips.items.first().driverId
        assertTrue(api.trips(null, driverId, 30, 0).items.all { it.driverId == driverId })
    }

    @Test
    fun alertReadMarksStayOnThePhone() = runBlocking {
        val before = api.alerts()
        val first = before.items.first { !it.read }
        api.markAlertRead(first.id)
        val after = api.alerts()
        assertEquals(before.unread - 1, after.unread)
        assertTrue(after.items.first { it.id == first.id }.read)
        assertEquals(after.unread, api.dashboard().unreadAlerts)
        assertEquals(after.unread, api.markAllAlertsRead().marked)
        assertEquals(0, api.alerts().unread)
        api.resetDemo()
        assertEquals(before.unread, api.alerts().unread)
    }

    @Test
    fun writesAskForTheLiveServerInsteadOfFakingIt() = runBlocking {
        listOf<suspend () -> Unit>(
            { api.predict(46) },
            { api.recordService(ServiceRecordRequest(46, "Brake Inspection")) },
        ).forEach { call ->
            try {
                call()
                fail("expected LiveServerRequiredException")
            } catch (e: LiveServerRequiredException) {
                assertTrue(e.message!!.contains("live AI server"))
            }
        }
    }
}
