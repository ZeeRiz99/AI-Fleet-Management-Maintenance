package com.zeeriz.fleetai.utils

import java.text.NumberFormat
import java.util.Locale
import kotlin.math.abs
import kotlin.math.roundToInt
import kotlin.math.roundToLong

/** Number formatting in Pakistani conventions (Rs, Lakh, Crore). */
object Format {
    private val grouping: NumberFormat = NumberFormat.getIntegerInstance(Locale.US)

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
}
