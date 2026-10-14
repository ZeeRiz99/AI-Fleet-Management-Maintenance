package com.zeeriz.fleetai.domain

import com.zeeriz.fleetai.domain.model.FuelCheckResult
import kotlinx.serialization.Serializable
import java.util.Locale
import kotlin.math.max
import kotlin.math.roundToLong

/** Per-vehicle baselines exported with the GitHub snapshot (static-api/v1/fuel/baselines.json). */
@Serializable
data class FuelBaselines(val threshold: Double, val window: Int, val vehicles: Map<String, VehicleBaseline> = emptyMap())

@Serializable
data class VehicleBaseline(val registration: String, val baselineKmPerL: Double, val fuelPrice: Double)

/**
 * The fuel-anomaly rule, identical to the backend's fuel check (api/fleet.py `fuel_check`): a fill-up is abnormal
 * when its km/l is below `threshold` x the vehicle's median km/l over its previous trips. Used on the phone when
 * the app reads the GitHub snapshot, so the check still runs for real without a server.
 */
object FuelRule {
    fun check(vehicleId: Int, baseline: VehicleBaseline, threshold: Double, distanceKm: Double, litres: Double): FuelCheckResult {
        require(distanceKm > 0 && litres > 0) { "Distance and litres must be positive." }
        val normal = baseline.baselineKmPerL
        val actual = distanceKm / litres
        val ratio = actual / normal
        val abnormal = ratio < threshold
        val expected = distanceKm / normal
        val excess = max(0.0, litres - expected)
        val excessCost = excess * baseline.fuelPrice
        val explanation = if (abnormal) {
            "${f2(actual)} km/l is only ${pct(ratio)}% of this vehicle's normal ${f2(normal)} km/l. " +
                "About ${f1(excess)} L (Rs ${String.format(Locale.US, "%,.0f", excessCost)}) more than expected - " +
                "check for a leak, theft or a wrong meter reading."
        } else {
            "${f2(actual)} km/l is ${pct(ratio)}% of this vehicle's usual ${f2(normal)} km/l " +
                "(flagged only below ${pct(threshold)}%)."
        }
        return FuelCheckResult(
            vehicleId = vehicleId,
            registration = baseline.registration,
            abnormal = abnormal,
            verdict = if (abnormal) "Abnormal" else "Normal",
            ratio = round(ratio, 3),
            threshold = threshold,
            baselineKmPerL = round(normal, 2),
            actualKmPerL = round(actual, 2),
            expectedLitres = round(expected, 1),
            excessLitres = round(excess, 1),
            excessCost = excessCost.roundToLong().toDouble(),
            explanation = explanation,
        )
    }

    private fun f1(v: Double) = String.format(Locale.US, "%.1f", v)
    private fun f2(v: Double) = String.format(Locale.US, "%.2f", v)
    private fun pct(v: Double) = String.format(Locale.US, "%.0f", v * 100)
    private fun round(v: Double, digits: Int): Double {
        var scale = 1.0
        repeat(digits) { scale *= 10 }
        return (v * scale).roundToLong() / scale
    }
}
