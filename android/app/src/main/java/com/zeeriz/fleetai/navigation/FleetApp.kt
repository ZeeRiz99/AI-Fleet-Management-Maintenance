package com.zeeriz.fleetai.navigation

import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.zeeriz.fleetai.data.local.AppSettings
import com.zeeriz.fleetai.di.AppContainer

/** Switch between bottom-bar sections without stacking copies of them (Home is the root after sign-in). */
fun NavHostController.navigateToTab(route: String) {
    navigate(route) {
        popUpTo(Routes.HOME) { saveState = true }
        launchSingleTop = true
        restoreState = true
    }
}

/** App shell: login gate, bottom bar for the five top-level sections, navigation graph. */
@Composable
fun FleetApp(container: AppContainer, settings: AppSettings) {
    val navController = rememberNavController()
    val startDestination = remember { if (settings.isLoggedIn) Routes.HOME else Routes.LOGIN }
    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = backStackEntry?.destination?.route
    val unreadAlerts by container.repository.unreadAlerts.collectAsStateWithLifecycle()
    val showBottomBar = TopLevelDestination.entries.any { it.route == currentRoute }

    // Session changes (sign-in, sign-out, expired token) move between the login screen and the app.
    LaunchedEffect(settings.isLoggedIn) {
        val route = navController.currentDestination?.route ?: return@LaunchedEffect
        if (!settings.isLoggedIn && route != Routes.LOGIN) {
            navController.navigate(Routes.LOGIN) { popUpTo(navController.graph.id) { inclusive = true } }
        } else if (settings.isLoggedIn && route == Routes.LOGIN) {
            navController.navigate(Routes.HOME) { popUpTo(Routes.LOGIN) { inclusive = true } }
        }
    }

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        bottomBar = {
            if (showBottomBar) {
                FleetBottomBar(currentRoute = currentRoute, unreadAlerts = unreadAlerts) { destination ->
                    navController.navigateToTab(destination.route)
                }
            }
        },
    ) { innerPadding ->
        FleetNavHost(
            navController = navController,
            startDestination = startDestination,
            // Only the bottom inset: each screen's own top app bar handles the status bar.
            modifier = Modifier.padding(bottom = innerPadding.calculateBottomPadding()),
        )
    }
}
