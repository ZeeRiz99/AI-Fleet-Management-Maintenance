package com.zeeriz.fleetai.ui.components

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.addPathNodes
import androidx.compose.ui.unit.dp

/**
 * Icons that are not in material-icons-core (path data from Material Icons, Apache 2.0).
 * Avoids pulling in the very large material-icons-extended artifact for a handful of glyphs.
 */
object FleetIcons {
    val Truck: ImageVector by lazy {
        icon(
            "Truck",
            "M20,8h-3L17,4L3,4c-1.1,0 -2,0.9 -2,2v11h2c0,1.66 1.34,3 3,3s3,-1.34 3,-3h6c0,1.66 1.34,3 3,3s3,-1.34 3,-3h2v-5l-3,-4z" +
                "M6,18.5c-0.83,0 -1.5,-0.67 -1.5,-1.5s0.67,-1.5 1.5,-1.5 1.5,0.67 1.5,1.5 -0.67,1.5 -1.5,1.5z" +
                "M19.5,9.5l1.96,2.5L17,12L17,9.5h2.5z" +
                "M18,18.5c-0.83,0 -1.5,-0.67 -1.5,-1.5s0.67,-1.5 1.5,-1.5 1.5,0.67 1.5,1.5 -0.67,1.5 -1.5,1.5z",
        )
    }
    val Fuel: ImageVector by lazy {
        icon(
            "Fuel",
            "M19.77,7.23l0.01,-0.01 -3.72,-3.72L15,4.56l2.11,2.11c-0.94,0.36 -1.61,1.26 -1.61,2.33 0,1.38 1.12,2.5 2.5,2.5 " +
                "0.36,0 0.69,-0.08 1,-0.21v7.21c0,0.55 -0.45,1 -1,1s-1,-0.45 -1,-1L17,14c0,-1.1 -0.9,-2 -2,-2h-1L14,5c0,-1.1 " +
                "-0.9,-2 -2,-2L6,3c-1.1,0 -2,0.9 -2,2v16h10v-7.5h1.5v5c0,1.38 1.12,2.5 2.5,2.5s2.5,-1.12 2.5,-2.5L20.5,9c0,-0.69 " +
                "-0.28,-1.32 -0.73,-1.77zM12,10L6,10L6,5h6v5zM18,10c-0.55,0 -1,-0.45 -1,-1s0.45,-1 1,-1 1,0.45 1,1 -0.45,1 -1,1z",
        )
    }
    val Route: ImageVector by lazy {
        icon(
            "Route",
            "M19,15.18V7c0,-2.21 -1.79,-4 -4,-4s-4,1.79 -4,4v10c0,1.1 -0.9,2 -2,2s-2,-0.9 -2,-2V8.82C8.16,8.4 9,7.3 9,6" +
                "c0,-1.66 -1.34,-3 -3,-3S3,4.34 3,6c0,1.3 0.84,2.4 2,2.82V17c0,2.21 1.79,4 4,4s4,-1.79 4,-4V7c0,-1.1 0.9,-2 2,-2" +
                "s2,0.9 2,2v8.18c-1.16,0.41 -2,1.51 -2,2.82c0,1.66 1.34,3 3,3s3,-1.34 3,-3C21,16.7 20.16,15.6 19,15.18z",
        )
    }
    val Sparkle: ImageVector by lazy {
        icon(
            "Sparkle",
            "M19,9l1.25,-2.75L23,5l-2.75,-1.25L19,1l-1.25,2.75L15,5l2.75,1.25L19,9z" +
                "M11.5,9.5L9,4L6.5,9.5L1,12l5.5,2.5L9,20l2.5,-5.5L17,12L11.5,9.5z" +
                "M19,15l-1.25,2.75L15,19l2.75,1.25L19,23l1.25,-2.75L23,19l-2.75,-1.25L19,15z",
        )
    }
    val Gauge: ImageVector by lazy {
        icon(
            "Gauge",
            "M20.38,8.57l-1.23,1.85a8,8 0,0 1,-0.22 7.58L5.07,18A8,8 0,0 1,15.58 6.85l1.85,-1.23A10,10 0,0 0,3.35 19" +
                "a2,2 0,0 0,1.72 1h13.85a2,2 0,0 0,1.74 -1a10,10 0,0 0,-0.27 -10.44z" +
                "M10.59,15.41a2,2 0,0 0,2.83 0l5.66,-8.49 -8.49,5.66a2,2 0,0 0,0 2.83z",
        )
    }
    val Chat: ImageVector by lazy {
        icon("Chat", "M20,2L4,2c-1.1,0 -2,0.9 -2,2v18l4,-4h14c1.1,0 2,-0.9 2,-2L22,4c0,-1.1 -0.9,-2 -2,-2z")
    }
    val Mic: ImageVector by lazy {
        icon(
            "Mic",
            "M12,14c1.66,0 2.99,-1.34 2.99,-3L15,5c0,-1.66 -1.34,-3 -3,-3S9,3.34 9,5v6c0,1.66 1.34,3 3,3z" +
                "M17.3,11c0,3 -2.54,5.1 -5.3,5.1S6.7,14 6.7,11L5,11c0,3.41 2.72,6.23 6,6.72L11,21h2v-3.28" +
                "c3.28,-0.48 6,-3.3 6,-6.72h-1.7z",
        )
    }

    private fun icon(name: String, path: String): ImageVector =
        ImageVector.Builder(name, 24.dp, 24.dp, 24f, 24f)
            .addPath(pathData = addPathNodes(path), fill = SolidColor(Color.Black))
            .build()
}
