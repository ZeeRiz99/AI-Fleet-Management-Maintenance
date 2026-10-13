package com.zeeriz.fleetai.ui.theme

import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Immutable
import androidx.compose.ui.graphics.Color

// One brand colour (blue) on a neutral slate palette; semantic colours are kept separate below.
private val Blue100 = Color(0xFFDBEAFE)
private val Blue400 = Color(0xFF60A5FA)
private val Blue600 = Color(0xFF2563EB)
private val Blue900 = Color(0xFF1E3A8A)
private val Slate50 = Color(0xFFF8FAFC)
private val Slate100 = Color(0xFFF1F5F9)
private val Slate200 = Color(0xFFE2E8F0)
private val Slate300 = Color(0xFFCBD5E1)
private val Slate400 = Color(0xFF94A3B8)
private val Slate500 = Color(0xFF64748B)
private val Slate600 = Color(0xFF475569)
private val Slate700 = Color(0xFF334155)
private val Slate800 = Color(0xFF1E293B)
private val Slate900 = Color(0xFF0F172A)
private val Ink = Color(0xFF0B1220)

val LightColors = lightColorScheme(
    primary = Blue600,
    onPrimary = Color.White,
    primaryContainer = Blue100,
    onPrimaryContainer = Blue900,
    inversePrimary = Blue400,
    secondary = Slate600,
    onSecondary = Color.White,
    secondaryContainer = Slate200,
    onSecondaryContainer = Slate900,
    tertiary = Color(0xFF0D9488),
    onTertiary = Color.White,
    tertiaryContainer = Color(0xFFCCFBF1),
    onTertiaryContainer = Color(0xFF134E4A),
    background = Color(0xFFF4F6FB),
    onBackground = Slate900,
    surface = Color.White,
    onSurface = Slate900,
    surfaceVariant = Color(0xFFEEF2F7),
    onSurfaceVariant = Slate500,
    surfaceTint = Blue600,
    inverseSurface = Slate800,
    inverseOnSurface = Slate100,
    error = Color(0xFFDC2626),
    onError = Color.White,
    errorContainer = Color(0xFFFEE2E2),
    onErrorContainer = Color(0xFF7F1D1D),
    outline = Slate300,
    outlineVariant = Slate200,
    scrim = Color.Black,
    surfaceBright = Color.White,
    surfaceDim = Slate200,
    surfaceContainerLowest = Color.White,
    surfaceContainerLow = Slate50,
    surfaceContainer = Slate100,
    surfaceContainerHigh = Color(0xFFE9EEF5),
    surfaceContainerHighest = Slate200,
)

val DarkColors = darkColorScheme(
    primary = Blue400,
    onPrimary = Ink,
    primaryContainer = Blue900,
    onPrimaryContainer = Blue100,
    inversePrimary = Blue600,
    secondary = Slate400,
    onSecondary = Ink,
    secondaryContainer = Slate700,
    onSecondaryContainer = Slate200,
    tertiary = Color(0xFF2DD4BF),
    onTertiary = Ink,
    tertiaryContainer = Color(0xFF134E4A),
    onTertiaryContainer = Color(0xFFCCFBF1),
    background = Ink,
    onBackground = Slate200,
    surface = Slate900,
    onSurface = Slate200,
    surfaceVariant = Slate800,
    onSurfaceVariant = Slate400,
    surfaceTint = Blue400,
    inverseSurface = Slate200,
    inverseOnSurface = Slate900,
    error = Color(0xFFF87171),
    onError = Ink,
    errorContainer = Color(0xFF7F1D1D),
    onErrorContainer = Color(0xFFFEE2E2),
    outline = Slate600,
    outlineVariant = Slate700,
    scrim = Color.Black,
    surfaceBright = Slate800,
    surfaceDim = Ink,
    surfaceContainerLowest = Ink,
    surfaceContainerLow = Color(0xFF111A2E),
    surfaceContainer = Color(0xFF162033),
    surfaceContainerHigh = Slate800,
    surfaceContainerHighest = Color(0xFF273449),
)

/** Semantic colours (success / warning / info / critical) used for statuses, never for decoration. */
@Immutable
data class SemanticColors(
    val success: Color,
    val successContainer: Color,
    val onSuccessContainer: Color,
    val warning: Color,
    val warningContainer: Color,
    val onWarningContainer: Color,
    val info: Color,
    val infoContainer: Color,
    val onInfoContainer: Color,
    val critical: Color,
    val criticalContainer: Color,
    val onCriticalContainer: Color,
)

val LightSemantic = SemanticColors(
    success = Color(0xFF16A34A), successContainer = Color(0xFFDCFCE7), onSuccessContainer = Color(0xFF14532D),
    warning = Color(0xFFD97706), warningContainer = Color(0xFFFEF3C7), onWarningContainer = Color(0xFF78350F),
    info = Color(0xFF0284C7), infoContainer = Color(0xFFE0F2FE), onInfoContainer = Color(0xFF0C4A6E),
    critical = Color(0xFFDC2626), criticalContainer = Color(0xFFFEE2E2), onCriticalContainer = Color(0xFF7F1D1D),
)

val DarkSemantic = SemanticColors(
    success = Color(0xFF4ADE80), successContainer = Color(0xFF14532D), onSuccessContainer = Color(0xFFDCFCE7),
    warning = Color(0xFFFBBF24), warningContainer = Color(0xFF78350F), onWarningContainer = Color(0xFFFEF3C7),
    info = Color(0xFF38BDF8), infoContainer = Color(0xFF0C4A6E), onInfoContainer = Color(0xFFE0F2FE),
    critical = Color(0xFFF87171), criticalContainer = Color(0xFF7F1D1D), onCriticalContainer = Color(0xFFFEE2E2),
)
