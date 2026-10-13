package com.zeeriz.fleetai.ui.components

import com.zeeriz.fleetai.ui.theme.Tone

/** Single place that maps backend status values to colours and labels. */
object StatusMapping {
    fun riskTone(tier: String): Tone = when (tier) {
        "High" -> Tone.CRITICAL
        "Medium" -> Tone.WARNING
        else -> Tone.SUCCESS
    }

    fun healthTone(band: String): Tone = when (band) {
        "Critical" -> Tone.CRITICAL
        "Watch" -> Tone.WARNING
        else -> Tone.SUCCESS
    }

    fun severityTone(severity: String): Tone = when (severity) {
        "critical" -> Tone.CRITICAL
        "warning" -> Tone.WARNING
        else -> Tone.INFO
    }

    fun serviceTone(status: String): Tone = when (status) {
        "overdue" -> Tone.CRITICAL
        "due_soon" -> Tone.WARNING
        "ok" -> Tone.SUCCESS
        else -> Tone.NEUTRAL
    }

    fun serviceLabel(status: String): String = when (status) {
        "overdue" -> "Overdue"
        "due_soon" -> "Due soon"
        "ok" -> "On track"
        else -> "No record"
    }

    /** Alert categories from the API, in the order shown as filter chips. */
    val alertCategories = listOf(
        "high_risk" to "High risk",
        "maintenance_overdue" to "Overdue",
        "maintenance_due" to "Due soon",
        "fuel_anomaly" to "Fuel anomaly",
        "health_warning" to "Health warning",
        "operational" to "Operational",
    )

    fun categoryLabel(category: String): String = alertCategories.firstOrNull { it.first == category }?.second ?: category

    fun vehicleStatusLabel(status: String): String = if (status == "maintenance") "In workshop" else "Active"
}
