package com.zeeriz.fleetai

import com.zeeriz.fleetai.data.remote.FleetJson
import com.zeeriz.fleetai.domain.model.Dashboard
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
}
