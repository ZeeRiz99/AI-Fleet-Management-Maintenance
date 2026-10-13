package com.zeeriz.fleetai.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

/** Meaning of a status, mapped to colours in one place so screens never pick raw colours. */
enum class Tone { NEUTRAL, BRAND, INFO, SUCCESS, WARNING, CRITICAL }

@Composable
fun Tone.accent(): Color = when (this) {
    Tone.NEUTRAL -> MaterialTheme.colorScheme.onSurfaceVariant
    Tone.BRAND -> MaterialTheme.colorScheme.primary
    Tone.INFO -> FleetTheme.semantic.info
    Tone.SUCCESS -> FleetTheme.semantic.success
    Tone.WARNING -> FleetTheme.semantic.warning
    Tone.CRITICAL -> FleetTheme.semantic.critical
}

@Composable
fun Tone.container(): Color = when (this) {
    Tone.NEUTRAL -> MaterialTheme.colorScheme.surfaceVariant
    Tone.BRAND -> MaterialTheme.colorScheme.primaryContainer
    Tone.INFO -> FleetTheme.semantic.infoContainer
    Tone.SUCCESS -> FleetTheme.semantic.successContainer
    Tone.WARNING -> FleetTheme.semantic.warningContainer
    Tone.CRITICAL -> FleetTheme.semantic.criticalContainer
}

@Composable
fun Tone.onContainer(): Color = when (this) {
    Tone.NEUTRAL -> MaterialTheme.colorScheme.onSurfaceVariant
    Tone.BRAND -> MaterialTheme.colorScheme.onPrimaryContainer
    Tone.INFO -> FleetTheme.semantic.onInfoContainer
    Tone.SUCCESS -> FleetTheme.semantic.onSuccessContainer
    Tone.WARNING -> FleetTheme.semantic.onWarningContainer
    Tone.CRITICAL -> FleetTheme.semantic.onCriticalContainer
}
