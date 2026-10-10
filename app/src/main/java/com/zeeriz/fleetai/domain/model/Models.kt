package com.zeeriz.fleetai.domain.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// Models mirror the FastAPI responses. JSON keys are snake_case; the shared Json config maps them to camelCase,
// and @SerialName is only needed where a key contains digits (e.g. litres_per_100km).

@Serializable
data class LoginRequest(val username: String, val password: String)

@Serializable
data class User(val username: String, val fullName: String? = null, val role: String = "viewer")

@Serializable
data class TokenResponse(val accessToken: String, val tokenType: String = "bearer", val expiresIn: Int = 0, val user: User)

@Serializable
data class Health(val status: String, val version: String = "", val asOf: String = "", val vehicles: Int = 0)

@Serializable
data class NextService(
    val service: String,
    val status: String,
    val dueInKm: Int? = null,
    val dueInDays: Int? = null,
    val overduePct: Int? = null,
)

@Serializable
data class VehicleSummary(
    val id: Int,
    val registration: String,
    val makeModel: String,
    val vehicleType: String,
    val fuelType: String,
    val year: Int,
    val depot: String,
    val status: String,
    val odometerKm: Int? = null,
    val healthScore: Int,
    val healthBand: String,
    val riskProbability: Double,
    val riskTier: String,
    val nextService: NextService? = null,
)

@Serializable
data class ScheduleItem(
    val vehicleId: Int,
    val registration: String,
    val depot: String,
    val service: String,
    val critical: Boolean,
    val intervalKm: Int? = null,
    val intervalDays: Int? = null,
    val lastDoneDate: String? = null,
    val lastDoneOdometerKm: Int? = null,
    val sinceLastKm: Int? = null,
    val sinceLastDays: Int? = null,
    val status: String,
    val dueInKm: Int? = null,
    val dueInDays: Int? = null,
    val dueDate: String? = null,
    val overduePct: Int? = null,
    val estimatedCost: Double = 0.0,
)

@Serializable
data class Alert(
    val id: String,
    val category: String,
    val severity: String,
    val title: String,
    val message: String,
    val vehicleId: Int? = null,
    val registration: String? = null,
    val date: String,
    val read: Boolean = false,
)

@Serializable
data class FuelMonth(
    val month: String,
    val km: Double = 0.0,
    val litres: Double = 0.0,
    val cost: Double = 0.0,
    val costPerKm: Double? = null,
    val kmPerLitre: Double? = null,
)

// ----------------------------------------------------------------------------- dashboard
@Serializable
data class Dashboard(
    val asOf: String,
    val dataStart: String,
    val dataEnd: String,
    val fleet: FleetStatus,
    val risk: RiskSummary,
    val fuel: FuelOverview,
    val maintenance: MaintenanceOverview,
    val health: HealthSummary,
    val recentAlerts: List<Alert> = emptyList(),
    val unreadAlerts: Int = 0,
)

@Serializable
data class FleetStatus(
    val totalVehicles: Int,
    val active: Int,
    val inMaintenance: Int,
    val critical: Int,
    val drivers: Int,
    val depots: Int,
)

@Serializable
data class RiskSummary(
    val high: Int,
    val medium: Int,
    val low: Int,
    val averageProbability: Double,
    val potentialSaving: Double = 0.0,
    val top: List<VehicleSummary> = emptyList(),
)

@Serializable
data class FuelOverview(
    val trips: Int = 0,
    val km: Double = 0.0,
    val litres: Double = 0.0,
    val cost: Double = 0.0,
    val costPerKm: Double? = null,
    val kmPerLitre: Double? = null,
    @SerialName("litres_per_100km") val litresPer100Km: Double? = null,
    val anomalies: Int = 0,
    val anomalyExcessCost: Double = 0.0,
    val monthly: List<FuelMonth> = emptyList(),
)

@Serializable
data class MaintenanceOverview(
    val overdue: Int = 0,
    val dueSoon: Int = 0,
    val vehiclesWithOverdue: Int = 0,
    @SerialName("completed_30d") val completed30d: Int = 0,
    @SerialName("spend_30d") val spend30d: Double = 0.0,
    @SerialName("spend_365d") val spend365d: Double = 0.0,
    @SerialName("breakdowns_365d") val breakdowns365d: Int = 0,
    val breakdownShare: Double = 0.0,
    val upcoming: List<ScheduleItem> = emptyList(),
)

@Serializable
data class HealthSummary(
    val average: Double,
    val good: Int,
    val watch: Int,
    val critical: Int,
    val formula: String = "",
)

// ----------------------------------------------------------------------------- vehicles / AI
@Serializable
data class Factor(
    val feature: String,
    val label: String,
    val display: String,
    val impact: Double,
    val direction: String,
)

@Serializable
data class Recommendation(
    val service: String,
    val overduePct: Int = 0,
    val serviceCost: Double = 0.0,
    val expectedLoss: Double = 0.0,
    val netSaving: Double = 0.0,
    val text: String,
)

@Serializable
data class Prediction(
    val vehicleId: Int,
    val registration: String,
    val riskProbability: Double,
    val riskTier: String,
    val healthScore: Int,
    val healthBand: String,
    val healthFormula: String = "",
    val explanation: String,
    val factors: List<Factor> = emptyList(),
    val recommendation: Recommendation,
    val model: String = "",
    val asOf: String = "",
    val scoredAt: String = "",
)

@Serializable
data class MonthlyEfficiency(val month: String, val kmPerL: Double)

@Serializable
data class VehicleFuel(
    @SerialName("trips_90d") val trips90d: Int = 0,
    @SerialName("km_90d") val km90d: Double = 0.0,
    @SerialName("litres_90d") val litres90d: Double = 0.0,
    @SerialName("cost_90d") val cost90d: Double = 0.0,
    @SerialName("km_per_l_90d") val kmPerL90d: Double? = null,
    @SerialName("cost_per_km_90d") val costPerKm90d: Double? = null,
    val monthlyKmPerL: List<MonthlyEfficiency> = emptyList(),
)

@Serializable
data class MaintenanceRecord(
    val id: Int,
    val vehicleId: Int,
    val registration: String? = null,
    val date: String,
    val service: String,
    val kind: String,
    val odometerKm: Int? = null,
    val cost: Double = 0.0,
    val downtimeDays: Int = 0,
    val notes: String? = null,
    val status: String = "Completed",
)

@Serializable
data class VehicleMaintenance(
    val totalCost: Double = 0.0,
    val preventiveCost: Double = 0.0,
    val breakdownCost: Double = 0.0,
    val breakdowns: Int = 0,
    val services: Int = 0,
    val history: List<MaintenanceRecord> = emptyList(),
)

@Serializable
data class Trip(
    val id: Int,
    val date: String,
    val startTime: String,
    val endTime: String,
    val durationMin: Int,
    val status: String = "Completed",
    val vehicleId: Int,
    val registration: String,
    val driverId: Int,
    val driver: String,
    val route: String,
    val distanceKm: Double,
    val fuelLitres: Double,
    val fuelCost: Double,
    val harshBrakingEvents: Int = 0,
    val fuelAnomaly: Boolean = false,
)

@Serializable
data class VehicleDetail(
    val id: Int,
    val registration: String,
    val makeModel: String,
    val vehicleType: String,
    val fuelType: String,
    val year: Int,
    val depot: String,
    val status: String,
    val odometerKm: Int? = null,
    val healthScore: Int,
    val healthBand: String,
    val riskProbability: Double,
    val riskTier: String,
    val nextService: NextService? = null,
    val ratedKmPerL: Double = 0.0,
    val prediction: Prediction,
    val fuel: VehicleFuel = VehicleFuel(),
    val maintenance: VehicleMaintenance = VehicleMaintenance(),
    val upcomingServices: List<ScheduleItem> = emptyList(),
    val recentTrips: List<Trip> = emptyList(),
)

@Serializable
data class ServiceRecordRequest(val vehicleId: Int, val service: String, val cost: Double? = null, val notes: String? = null)

@Serializable
data class ServiceRecordResult(val record: MaintenanceRecord, val before: Prediction, val after: Prediction)

// ----------------------------------------------------------------------------- maintenance
@Serializable
data class MaintenanceSummary(
    val overdue: Int = 0,
    val dueSoon: Int = 0,
    val vehiclesWithOverdue: Int = 0,
    @SerialName("completed_30d") val completed30d: Int = 0,
    @SerialName("spend_30d") val spend30d: Double = 0.0,
    @SerialName("spend_365d") val spend365d: Double = 0.0,
    @SerialName("breakdowns_365d") val breakdowns365d: Int = 0,
    val breakdownShare: Double = 0.0,
)

@Serializable
data class MaintenancePage(val total: Int, val items: List<MaintenanceRecord>)

// ----------------------------------------------------------------------------- fuel
@Serializable
data class FuelTotals(
    val trips: Int = 0,
    val km: Double = 0.0,
    val litres: Double = 0.0,
    val cost: Double = 0.0,
    val costPerKm: Double? = null,
    val kmPerLitre: Double? = null,
    @SerialName("litres_per_100km") val litresPer100Km: Double? = null,
    val anomalies: Int = 0,
    val anomalyExcessCost: Double = 0.0,
)

@Serializable
data class FuelGroup(
    val name: String,
    val km: Double = 0.0,
    val litres: Double = 0.0,
    val cost: Double = 0.0,
    val trips: Int = 0,
    val costPerKm: Double? = null,
    val kmPerLitre: Double? = null,
    val vehicleId: Int? = null,
)

@Serializable
data class FuelPrice(val month: String, val petrol: Double? = null, val diesel: Double? = null)

@Serializable
data class FuelSummary(
    val days: Int,
    val periodEnd: String = "",
    val totals: FuelTotals,
    val byVehicle: List<FuelGroup> = emptyList(),
    val byDepot: List<FuelGroup> = emptyList(),
    val byModel: List<FuelGroup> = emptyList(),
    val monthly: List<FuelMonth> = emptyList(),
    val priceMonthly: List<FuelPrice> = emptyList(),
)

@Serializable
data class FuelAnomaly(
    val tripId: Int,
    val date: String,
    val vehicleId: Int,
    val registration: String? = null,
    val driver: String? = null,
    val route: String = "",
    val distanceKm: Double = 0.0,
    val fuelLitres: Double = 0.0,
    val expectedLitres: Double = 0.0,
    val baselineKmPerL: Double = 0.0,
    val actualKmPerL: Double = 0.0,
    val ratio: Double = 0.0,
    val excessLitres: Double = 0.0,
    val excessCost: Double = 0.0,
    val explanation: String = "",
)

@Serializable
data class FuelAnomalies(
    val days: Int,
    val count: Int,
    val excessLitres: Double = 0.0,
    val excessCost: Double = 0.0,
    val vehiclesAffected: Int = 0,
    val threshold: Double = 0.0,
    val method: String = "",
    val items: List<FuelAnomaly> = emptyList(),
)

@Serializable
data class FuelCheckRequest(val vehicleId: Int, val distanceKm: Double, val fuelLitres: Double)

@Serializable
data class FuelCheckResult(
    val vehicleId: Int,
    val registration: String,
    val abnormal: Boolean,
    val verdict: String,
    val ratio: Double,
    val threshold: Double,
    val baselineKmPerL: Double,
    val actualKmPerL: Double,
    val expectedLitres: Double,
    val excessLitres: Double,
    val excessCost: Double,
    val explanation: String,
)
