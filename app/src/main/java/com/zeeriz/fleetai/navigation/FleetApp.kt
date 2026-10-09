package com.zeeriz.fleetai.navigation

import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.zeeriz.fleetai.data.local.AppSettings
import com.zeeriz.fleetai.di.AppContainer

/** App shell: bottom bar for the five top-level sections + the navigation graph. */
@Composable
fun FleetApp(container: AppContainer, settings: AppSettings) {
    val navController = rememberNavController()
    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = backStackEntry?.destination?.route
    val showBottomBar = TopLevelDestination.entries.any { it.route == currentRoute }

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        bottomBar = {
            if (showBottomBar) {
                FleetBottomBar(currentRoute = currentRoute, unreadAlerts = 0) { destination ->
                    navController.navigate(destination.route) {
                        popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                        launchSingleTop = true
                        restoreState = true
                    }
                }
            }
        },
    ) { innerPadding ->
        FleetNavHost(
            navController = navController,
            container = container,
            settings = settings,
            // Only the bottom inset: each screen's own top app bar handles the status bar.
            modifier = Modifier.padding(bottom = innerPadding.calculateBottomPadding()),
        )
    }
}
