package com.zeeriz.fleetai.ui.components

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.zeeriz.fleetai.presentation.ScreenState
import com.zeeriz.fleetai.ui.theme.Tone
import com.zeeriz.fleetai.ui.theme.accent
import com.zeeriz.fleetai.ui.theme.container
import com.zeeriz.fleetai.ui.theme.onContainer
import com.zeeriz.fleetai.utils.Format

/**
 * Standard handling for a data screen: skeleton on first load, full-screen error with retry when there is
 * nothing to show, otherwise the content inside pull-to-refresh.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun <T> StateContent(
    state: ScreenState<T>,
    onRetry: () -> Unit,
    onRefresh: () -> Unit,
    modifier: Modifier = Modifier,
    content: @Composable (T) -> Unit,
) {
    val data = state.data
    when {
        data == null && state.loading -> LoadingSkeleton(modifier)
        data == null -> ErrorState(
            title = "Couldn't load data",
            message = state.error ?: "Something went wrong.",
            modifier = modifier,
            onRetry = onRetry,
        )
        else -> PullToRefreshBox(isRefreshing = state.refreshing, onRefresh = onRefresh, modifier = modifier.fillMaxSize()) {
            content(data)
        }
    }
}

/** Shown above content when it came from the offline cache or the last refresh failed. */
@Composable
fun DataStatusBanner(state: ScreenState<*>, modifier: Modifier = Modifier) {
    val saved = state.offlineSince
    when {
        saved != null -> Banner("Offline — showing data saved ${Format.relative(saved)}. Pull down to retry.", Tone.WARNING, modifier)
        state.error != null && state.data != null -> Banner(state.error, Tone.CRITICAL, modifier)
    }
}

@Composable
fun Banner(text: String, tone: Tone, modifier: Modifier = Modifier) {
    Surface(modifier = modifier.fillMaxWidth(), shape = MaterialTheme.shapes.medium, color = tone.container()) {
        Row(Modifier.padding(horizontal = 14.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(
                if (tone == Tone.CRITICAL || tone == Tone.WARNING) Icons.Filled.Warning else Icons.Filled.Info,
                contentDescription = null,
                tint = tone.accent(),
                modifier = Modifier.size(18.dp),
            )
            Spacer(Modifier.width(10.dp))
            Text(text, style = MaterialTheme.typography.bodySmall, color = tone.onContainer())
        }
    }
}
