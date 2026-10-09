package com.zeeriz.fleetai.utils

import android.text.format.DateUtils
import java.text.NumberFormat
import java.time.LocalDate
import java.time.YearMonth
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.abs
import kotlin.math.roundToInt
import kotlin.math.roundToLong

/** Number and date formatting in Pakistani conventions (Rs, Lakh, Crore). */
object Format {
    private val grouping: NumberFormat = NumberFormat.getIntegerInstance(Locale.US)
    private val dayFormat = DateTimeFormatter.ofPattern("d MMM yyyy", Locale.US)
    private val monthFormat = DateTimeFormatter.ofPattern("MMM yy", Locale.US)

    fun number(value: Double): String = grouping.format(value.roundToLong())
    fun number(value: Int): String = grouping.format(value.toLong())
    fun rupees(value: Double): String = "Rs " + number(value)

    /** Compact rupees for tiles: Rs 1.95 Cr, Rs 39.9 Lakh, else the full amount. */
    fun rupeesShort(value: Double): String = when {
        abs(value) >= 1e7 -> "Rs %.2f Cr".format(Locale.US, value / 1e7)
        abs(value) >= 1e5 -> "Rs %.1f Lakh".format(Locale.US, value / 1e5)
        else -> rupees(value)
    }

    fun percent(fraction: Double): String = "${(fraction * 100).roundToInt()}%"
    fun decimal(value: Double, digits: Int = 1): String = "%.${digits}f".format(Locale.US, value)
    fun km(value: Double): String = number(value) + " km"

    /** "2026-01-01" -> "1 Jan 2026" (falls back to the input). */
    fun date(iso: String): String = runCatching { LocalDate.parse(iso.take(10)).format(dayFormat) }.getOrDefault(iso)

    /** "2025-07" -> "Jul 25". */
    fun month(yearMonth: String): String = runCatching { YearMonth.parse(yearMonth).format(monthFormat) }.getOrDefault(yearMonth)

    /** "5 minutes ago" style text for a past timestamp. */
    fun relative(epochMillis: Long): String =
        DateUtils.getRelativeTimeSpanString(epochMillis, System.currentTimeMillis(), DateUtils.MINUTE_IN_MILLIS).toString()

    fun days(n: Int): String = if (n == 1) "1 day" else "${number(n)} days"

    /** "Due in 1,200 km" / "Overdue by 3,400 km (17%)" style text for a service. */
    fun dueText(dueInKm: Int?, dueInDays: Int?, overduePct: Int?): String = when {
        dueInKm != null && dueInKm < 0 -> "Overdue by ${number(-dueInKm)} km" + (overduePct?.let { " ($it%)" } ?: "")
        dueInKm != null -> "Due in ${number(dueInKm)} km" + (dueInDays?.let { " · ~${days(it)}" } ?: "")
        dueInDays != null && dueInDays < 0 -> "Overdue by ${days(-dueInDays)}"
        dueInDays != null -> "Due in ${days(dueInDays)}"
        else -> "No service record yet"
    }
}
