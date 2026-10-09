package com.zeeriz.fleetai.ui.screens

import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import com.zeeriz.fleetai.ui.components.EmptyState
import com.zeeriz.fleetai.ui.components.FleetIcons
import com.zeeriz.fleetai.ui.components.FleetScaffold

/** Temporary screen for sections that are built in later phases (keeps navigation testable now). */
@Composable
fun PlaceholderScreen(title: String, phase: Int, onBack: (() -> Unit)? = null) {
    FleetScaffold(title = title, onBack = onBack) { padding ->
        EmptyState(
            title = "$title — coming in phase $phase",
            message = "Navigation to this screen works. Its content is built in phase $phase of the plan.",
            icon = FleetIcons.Sparkle,
            modifier = Modifier.padding(padding),
        )
    }
}
