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
import com.zeeriz.fleetai.ui.screens.LoginScreen
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
    val dashboardActions = DashboardActions(
        openVehicle = { navController.navigate(Routes.vehicleDetail(it)) },
        openVehicles = { navController.navigateToTab(Routes.VEHICLES) },
        openMaintenance = { navController.navigateToTab(Routes.MAINTENANCE) },
        openAlerts = { navController.navigateToTab(Routes.ALERTS) },
        openFuel = { navController.navigate(Routes.FUEL) },
        openDrivers = { navController.navigate(Routes.DRIVERS) },
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
        composable(Routes.MAINTENANCE) { PlaceholderScreen("Maintenance", phase = 5) }
        composable(Routes.ALERTS) { PlaceholderScreen("Alerts", phase = 8) }
        composable(Routes.PROFILE) { ProfileScreen() }

        composable(
            Routes.VEHICLE_DETAIL,
            arguments = listOf(navArgument(Routes.VEHICLE_ID) { type = NavType.IntType }),
        ) { VehicleDetailScreen(onBack = back) }
        composable(Routes.FUEL) { PlaceholderScreen("Fuel analytics", phase = 6, onBack = back) }
        composable(Routes.DRIVERS) { PlaceholderScreen("Drivers", phase = 7, onBack = back) }
        composable(
            Routes.DRIVER_DETAIL,
            arguments = listOf(navArgument(Routes.DRIVER_ID) { type = NavType.IntType }),
        ) { entry ->
            PlaceholderScreen("Driver #${entry.arguments?.getInt(Routes.DRIVER_ID)}", phase = 7, onBack = back)
        }
        composable(Routes.TRIPS) { PlaceholderScreen("Trips", phase = 7, onBack = back) }
    }
}
