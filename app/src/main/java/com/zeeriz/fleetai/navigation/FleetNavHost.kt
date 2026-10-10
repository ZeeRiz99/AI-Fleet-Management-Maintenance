package com.zeeriz.fleetai.navigation

import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.zeeriz.fleetai.ui.screens.DashboardActions
import com.zeeriz.fleetai.ui.screens.DashboardScreen
import com.zeeriz.fleetai.ui.screens.DriverDetailScreen
import com.zeeriz.fleetai.ui.screens.DriversScreen
import com.zeeriz.fleetai.ui.screens.TripsScreen
import com.zeeriz.fleetai.ui.screens.FuelScreen
import com.zeeriz.fleetai.ui.screens.LoginScreen
import com.zeeriz.fleetai.ui.screens.MaintenanceScreen
import com.zeeriz.fleetai.ui.screens.PlaceholderScreen
import com.zeeriz.fleetai.ui.screens.ProfileScreen
import com.zeeriz.fleetai.ui.screens.VehicleDetailScreen
import com.zeeriz.fleetai.ui.screens.VehiclesScreen

@Composable
fun FleetNavHost(
    navController: NavHostController,
    startDestination: String,
    modifier: Modifier = Modifier,
) {
    val back: () -> Unit = { navController.popBackStack() }
    val openVehicle: (Int) -> Unit = { navController.navigate(Routes.vehicleDetail(it)) }
    val dashboardActions = DashboardActions(
        openVehicle = { navController.navigate(Routes.vehicleDetail(it)) },
        openVehicles = { navController.navigateToTab(Routes.VEHICLES) },
        openMaintenance = { navController.navigateToTab(Routes.MAINTENANCE) },
        openAlerts = { navController.navigateToTab(Routes.ALERTS) },
        openFuel = { navController.navigate(Routes.FUEL) },
        openDrivers = { navController.navigate(Routes.DRIVERS) },
        openTrips = { navController.navigate(Routes.TRIPS) },
    )
    NavHost(
        navController = navController,
        startDestination = startDestination,
        modifier = modifier,
        enterTransition = { fadeIn(tween(180)) },
        exitTransition = { fadeOut(tween(120)) },
        popEnterTransition = { fadeIn(tween(180)) },
        popExitTransition = { fadeOut(tween(120)) },
    ) {
        composable(Routes.LOGIN) { LoginScreen() }

        composable(Routes.HOME) { DashboardScreen(dashboardActions) }
        composable(Routes.VEHICLES) { VehiclesScreen(onOpenVehicle = { navController.navigate(Routes.vehicleDetail(it)) }) }
        composable(Routes.MAINTENANCE) { MaintenanceScreen(onOpenVehicle = { navController.navigate(Routes.vehicleDetail(it)) }) }
        composable(Routes.ALERTS) { PlaceholderScreen("Alerts", phase = 8) }
        composable(Routes.PROFILE) { ProfileScreen() }

        composable(
            Routes.VEHICLE_DETAIL,
            arguments = listOf(navArgument(Routes.VEHICLE_ID) { type = NavType.IntType }),
        ) { VehicleDetailScreen(onBack = back) }
        composable(Routes.FUEL) { FuelScreen(onBack = back, onOpenVehicle = { navController.navigate(Routes.vehicleDetail(it)) }) }
        composable(Routes.DRIVERS) { DriversScreen(onBack = back, onOpenDriver = { navController.navigate(Routes.driverDetail(it)) }) }
        composable(
            Routes.DRIVER_DETAIL,
            arguments = listOf(navArgument(Routes.DRIVER_ID) { type = NavType.IntType }),
        ) { DriverDetailScreen(onBack = back, onOpenVehicle = openVehicle) }
        composable(Routes.TRIPS) { TripsScreen(onBack = back, onOpenVehicle = openVehicle) }
    }
}
