package edu.amrita.feedbackautomater.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Error
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import edu.amrita.feedbackautomater.model.LogLevel
import edu.amrita.feedbackautomater.ui.MainUiState
import edu.amrita.feedbackautomater.ui.MainViewModel
import edu.amrita.feedbackautomater.ui.components.EmptyState
import edu.amrita.feedbackautomater.ui.theme.Semantic

@Composable
fun ActivityLogScreen(state: MainUiState, vm: MainViewModel, modifier: Modifier = Modifier) {
    val listState = rememberLazyListState()
    val clipboard = LocalClipboardManager.current

    LaunchedEffect(state.logs.size) {
        if (state.logs.isNotEmpty()) listState.animateScrollToItem(state.logs.lastIndex)
    }

    Column(modifier = modifier.fillMaxSize()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 8.dp),
            horizontalArrangement = Arrangement.End
        ) {
            TextButton(
                onClick = {
                    clipboard.setText(AnnotatedString(state.logs.joinToString("\n") { "${it.timestamp} ${it.message}" }))
                },
                enabled = state.logs.isNotEmpty()
            ) { Text("Copy log") }
            TextButton(
                onClick = { vm.clearLogs() },
                enabled = state.logs.isNotEmpty() && !state.isRunning
            ) { Text("Clear") }
        }

        if (state.logs.isEmpty()) {
            EmptyState(
                title = "Nothing has run yet",
                body = "Progress from every run shows up here while it happens."
            )
        } else {
            LazyColumn(
                state = listState,
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                itemsIndexed(state.logs, key = { index, entry -> "$index-${entry.timestamp}" }) { _, entry ->
                    val color = when (entry.level) {
                        LogLevel.ERROR -> MaterialTheme.colorScheme.error
                        LogLevel.WARN -> Semantic.colors.warning
                        LogLevel.SUCCESS -> Semantic.colors.success
                        LogLevel.INFO -> MaterialTheme.colorScheme.onSurface
                    }
                    Row(verticalAlignment = Alignment.Top) {
                        Text(
                            text = entry.timestamp,
                            fontFamily = FontFamily.Monospace,
                            fontSize = 12.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(top = 2.dp)
                        )
                        Spacer(Modifier.width(10.dp))
                        if (entry.level == LogLevel.ERROR || entry.level == LogLevel.WARN) {
                            Icon(
                                imageVector = if (entry.level == LogLevel.ERROR) Icons.Rounded.Error else Icons.Rounded.Warning,
                                contentDescription = if (entry.level == LogLevel.ERROR) "Error" else "Warning",
                                tint = color,
                                modifier = Modifier
                                    .padding(top = 2.dp, end = 6.dp)
                                    .size(16.dp)
                            )
                        }
                        Text(
                            text = entry.message,
                            style = MaterialTheme.typography.bodyMedium,
                            color = color,
                            modifier = Modifier.weight(1f)
                        )
                    }
                }
            }
        }
    }
}
