package com.zeeriz.fleetai

import com.zeeriz.fleetai.data.remote.FleetJson
import com.zeeriz.fleetai.domain.model.AlertList
import com.zeeriz.fleetai.domain.model.Dashboard
import com.zeeriz.fleetai.domain.model.ModelInfo
import com.zeeriz.fleetai.presentation.AlertFilter
import com.zeeriz.fleetai.presentation.applyFilter
import com.zeeriz.fleetai.presentation.markRead
import com.zeeriz.fleetai.domain.model.DriverDetail
import com.zeeriz.fleetai.domain.model.DriverList
import com.zeeriz.fleetai.domain.model.TripPage
import com.zeeriz.fleetai.presentation.DriverSort
import com.zeeriz.fleetai.presentation.sortDrivers
import com.zeeriz.fleetai.domain.model.FuelAnomalies
import com.zeeriz.fleetai.domain.model.FuelSummary
import com.zeeriz.fleetai.domain.model.MaintenancePage
import com.zeeriz.fleetai.domain.model.MaintenanceSummary
import com.zeeriz.fleetai.domain.model.ScheduleItem
import com.zeeriz.fleetai.domain.model.VehicleDetail
import com.zeeriz.fleetai.domain.model.VehicleSummary
import com.zeeriz.fleetai.presentation.VehicleFilters
import com.zeeriz.fleetai.presentation.VehicleSort
import com.zeeriz.fleetai.presentation.applyFilters
import kotlinx.serialization.builtins.ListSerializer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Contract tests: real responses captured from the FastAPI server (src/test/resources/api) must parse into the
 * app's models. If the API changes shape, these fail on the build machine instead of on a phone.
 */
class ApiContractTest {
    private fun fixture(name: String): String =
        requireNotNull(javaClass.classLoader?.getResource("api/$name")) { "missing fixture $name" }.readText()

    private val vehicles by lazy { FleetJson.decodeFromString(ListSerializer(VehicleSummary.serializer()), fixture("vehicles.json")) }

    @Test
    fun dashboardParses() {
        val d = FleetJson.decodeFromString(Dashboard.serializer(), fixture("dashboard.json"))
        assertEquals(58, d.fleet.totalVehicles)
        assertEquals(58, d.risk.high + d.risk.medium + d.risk.low)
        assertEquals(5, d.risk.top.size)
        assertTrue(d.fuel.monthly.size == 12 && d.fuel.cost > 0)
        assertTrue(d.recentAlerts.isNotEmpty() && d.maintenance.upcoming.isNotEmpty())
    }

    @Test
    fun vehicleListParses() {
        assertEquals(58, vehicles.size)
        assertTrue(vehicles.all { it.healthScore in 0..100 && it.riskProbability in 0.0..1.0 })
    }

    @Test
    fun vehicleDetailParses() {
        val v = FleetJson.decodeFromString(VehicleDetail.serializer(), fixture("vehicle_46.json"))
        assertEquals(46, v.id)
        assertTrue(v.prediction.explanation.contains(v.registration))
        assertTrue(v.prediction.factors.isNotEmpty() && v.upcomingServices.size == 10)
        assertTrue(v.maintenance.history.isNotEmpty() && v.recentTrips.isNotEmpty() && v.fuel.monthlyKmPerL.isNotEmpty())
    }

    @Test
    fun filtersAndSorting() {
        val high = vehicles.applyFilters(VehicleFilters(tier = "High"))
        assertTrue(high.isNotEmpty() && high.all { it.riskTier == "High" })
        val byRisk = vehicles.applyFilters(VehicleFilters())
        assertEquals(byRisk.map { it.riskProbability }, byRisk.map { it.riskProbability }.sortedDescending())
        val byHealth = vehicles.applyFilters(VehicleFilters(sort = VehicleSort.HEALTH))
        assertEquals(byHealth.map { it.healthScore }, byHealth.map { it.healthScore }.sorted())
        val reg = vehicles.first().registration
        assertEquals(listOf(reg), vehicles.applyFilters(VehicleFilters(query = reg.lowercase())).map { it.registration })
        assertTrue(vehicles.applyFilters(VehicleFilters(query = "zzz-no-match")).isEmpty())
    }

    @Test
    fun maintenanceParses() {
        val summary = FleetJson.decodeFromString(MaintenanceSummary.serializer(), fixture("maintenance_summary.json"))
        val overdue = FleetJson.decodeFromString(ListSerializer(ScheduleItem.serializer()), fixture("schedule_overdue.json"))
        val history = FleetJson.decodeFromString(MaintenancePage.serializer(), fixture("history.json"))
        assertEquals(summary.overdue, overdue.size)
        assertTrue(overdue.all { it.status == "overdue" && (it.overduePct ?: 0) >= 0 })
        assertTrue(history.total > history.items.size && history.items.isNotEmpty())
    }

    @Test
    fun fuelParses() {
        val s = FleetJson.decodeFromString(FuelSummary.serializer(), fixture("fuel_summary_30.json"))
        val a = FleetJson.decodeFromString(FuelAnomalies.serializer(), fixture("fuel_anomalies_90.json"))
        assertEquals(30, s.days)
        assertTrue(s.totals.cost > 0 && s.byVehicle.size == 58 && s.byVehicle.all { it.vehicleId != null })
        assertTrue(s.byDepot.size == 3 && s.monthly.isNotEmpty() && s.priceMonthly.isNotEmpty())
        assertTrue(a.count > 0 && a.items.all { it.actualKmPerL < it.baselineKmPerL && it.explanation.isNotBlank() })
    }

    @Test
    fun driversAndTripsParse() {
        val list = FleetJson.decodeFromString(DriverList.serializer(), fixture("drivers.json"))
        assertEquals(24, list.items.size)
        assertTrue(list.items.all { it.safetyScore in 0..100 && it.performanceScore in 0..100 })
        val worst = list.items.sortDrivers(DriverSort.SAFETY_LOW)
        assertTrue(worst.first().safetyScore <= worst.last().safetyScore)
        val d = FleetJson.decodeFromString(DriverDetail.serializer(), fixture("driver_1.json"))
        assertTrue(d.recentTrips.isNotEmpty() && d.safetyFormula.isNotBlank())
        val trips = FleetJson.decodeFromString(TripPage.serializer(), fixture("trips.json"))
        assertTrue(trips.total > 40000 && trips.items.size == 30 && trips.active == 0)
    }

    @Test
    fun alertsParseFilterAndMarkRead() {
        val list = FleetJson.decodeFromString(AlertList.serializer(), fixture("alerts.json"))
        assertTrue(list.total > 0 && list.items.size == list.total)
        val categories = list.items.map { it.category }.toSet()
        assertTrue(categories.containsAll(setOf("high_risk", "maintenance_overdue", "fuel_anomaly")))
        val highRisk = list.items.applyFilter(AlertFilter(category = "high_risk"))
        assertTrue(highRisk.isNotEmpty() && highRisk.all { it.severity == "critical" })
        val first = list.items.first { !it.read }
        val after = list.markRead(setOf(first.id))
        assertEquals(list.unread - 1, after.unread)
        assertTrue(after.items.first { it.id == first.id }.read)
        assertEquals(after.unread, after.markRead(setOf(first.id)).unread)   // marking twice does not double count
        assertTrue(after.items.applyFilter(AlertFilter(unreadOnly = true)).none { it.id == first.id })
    }

    @Test
    fun modelInfoParses() {
        val m = FleetJson.decodeFromString(ModelInfo.serializer(), fixture("model_info.json"))
        assertEquals("XGBoost", m.riskModel.metrics.first().model)
        assertTrue(m.riskModel.metrics.first().rocAuc!! > 0.6)
        assertTrue(m.explainability.isNotEmpty() && m.fuelAnomaly.metrics.isNotEmpty() && m.dataNote.contains("simulated"))
    }
}
