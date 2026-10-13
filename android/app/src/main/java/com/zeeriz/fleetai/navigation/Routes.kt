package com.zeeriz.fleetai.navigation

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Person
import androidx.compose.ui.graphics.vector.ImageVector
import com.zeeriz.fleetai.ui.components.FleetIcons

object Routes {
    const val LOGIN = "login"

    const val HOME = "home"
    const val VEHICLES = "vehicles"
    const val MAINTENANCE = "maintenance"
    const val ALERTS = "alerts"
    const val PROFILE = "profile"

    const val VEHICLE_ID = "vehicleId"
    const val VEHICLE_DETAIL = "vehicles/{$VEHICLE_ID}"
    fun vehicleDetail(id: Int) = "vehicles/$id"

    const val FUEL = "fuel"
    const val DRIVERS = "drivers"
    const val DRIVER_ID = "driverId"
    const val DRIVER_DETAIL = "drivers/{$DRIVER_ID}"
    fun driverDetail(id: Int) = "drivers/$id"
    const val TRIPS = "trips"
}

/** The five sections in the bottom bar; everything else opens from these. */
enum class TopLevelDestination(val route: String, val label: String, val icon: ImageVector) {
    HOME(Routes.HOME, "Home", Icons.Filled.Home),
    VEHICLES(Routes.VEHICLES, "Vehicles", FleetIcons.Truck),
    MAINTENANCE(Routes.MAINTENANCE, "Maintenance", Icons.Filled.Build),
    ALERTS(Routes.ALERTS, "Alerts", Icons.Filled.Notifications),
    PROFILE(Routes.PROFILE, "Profile", Icons.Filled.Person),
}
