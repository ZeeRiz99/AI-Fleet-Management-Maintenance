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
import com.zeeriz.fleetai.data.local.AppSettings
import com.zeeriz.fleetai.di.AppContainer
import com.zeeriz.fleetai.ui.screens.PhaseHomeScreen
import com.zeeriz.fleetai.ui.screens.PlaceholderScreen
import com.zeeriz.fleetai.ui.screens.ProfileScreen

@Composable
fun FleetNavHost(
    navController: NavHostController,
    container: AppContainer,
    settings: AppSettings,
    modifier: Modifier = Modifier,
) {
    val back: () -> Unit = { navController.popBackStack() }
    NavHost(
        navController = navController,
        startDestination = Routes.HOME,
        modifier = modifier,
        enterTransition = { fadeIn(tween(180)) },
        exitTransition = { fadeOut(tween(120)) },
        popEnterTransition = { fadeIn(tween(180)) },
        popExitTransition = { fadeOut(tween(120)) },
    ) {
        composable(Routes.HOME) { PhaseHomeScreen(onNavigate = { navController.navigate(it) }) }
        composable(Routes.VEHICLES) { PlaceholderScreen("Vehicles", phase = 3) }
        composable(Routes.MAINTENANCE) { PlaceholderScreen("Maintenance", phase = 5) }
        composable(Routes.ALERTS) { PlaceholderScreen("Alerts", phase = 8) }
        composable(Routes.PROFILE) { ProfileScreen() }

        composable(
            Routes.VEHICLE_DETAIL,
            arguments = listOf(navArgument(Routes.VEHICLE_ID) { type = NavType.IntType }),
        ) { entry ->
            PlaceholderScreen("Vehicle #${entry.arguments?.getInt(Routes.VEHICLE_ID)}", phase = 4, onBack = back)
        }
        composable(Routes.FUEL) { PlaceholderScreen("Fuel analytics", phase = 6, onBack = back) }
        composable(Routes.DRIVERS) { PlaceholderScreen("Drivers", phase = 7, onBack = back) }
        composable(
            Routes.DRIVER_DETAIL,
            arguments = listOf(navArgument(Routes.DRIVER_ID) { type = NavType.IntType }),
        ) { entry ->
            PlaceholderScreen("Driver #${entry.arguments?.getInt(Routes.DRIVER_ID)}", phase = 7, onBack = back)
        }
        composable(Routes.TRIPS) { PlaceholderScreen("Trips", phase = 7, onBack = back) }
        composable(Routes.LOGIN) { PlaceholderScreen("Sign in", phase = 3, onBack = back) }
    }
}
