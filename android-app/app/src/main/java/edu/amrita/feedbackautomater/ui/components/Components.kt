package edu.amrita.feedbackautomater.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Error
import androidx.compose.material.icons.rounded.Schedule
import androidx.compose.material.icons.rounded.Stop
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import edu.amrita.feedbackautomater.model.ItemStatus
import edu.amrita.feedbackautomater.model.RatingScheme
import edu.amrita.feedbackautomater.ui.theme.Semantic

fun statusLabel(status: ItemStatus): String = when (status) {
    ItemStatus.PENDING -> "Waiting"
    ItemStatus.PROCESSING -> "Working"
    ItemStatus.DONE -> "Done"
    ItemStatus.SKIPPED -> "Already done"
    ItemStatus.FAILED -> "Failed"
}

@Composable
fun StatusIcon(status: ItemStatus, modifier: Modifier = Modifier) {
    val iconModifier = modifier.size(22.dp)
    when (status) {
        ItemStatus.PROCESSING -> CircularProgressIndicator(
            modifier = modifier.size(20.dp),
            strokeWidth = 2.dp
        )
        ItemStatus.DONE -> Icon(
            Icons.Rounded.CheckCircle,
            contentDescription = "Done",
            tint = Semantic.colors.success,
            modifier = iconModifier
        )
        ItemStatus.SKIPPED -> Icon(
            Icons.Rounded.CheckCircle,
            contentDescription = "Already done",
            tint = MaterialTheme.colorScheme.outline,
            modifier = iconModifier
        )
        ItemStatus.FAILED -> Icon(
            Icons.Rounded.Error,
            contentDescription = "Failed",
            tint = MaterialTheme.colorScheme.error,
            modifier = iconModifier
        )
        ItemStatus.PENDING -> Icon(
            Icons.Rounded.Schedule,
            contentDescription = "Waiting",
            tint = MaterialTheme.colorScheme.outline,
            modifier = iconModifier
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RatingDropdown(
    label: String,
    selected: RatingScheme,
    options: List<RatingScheme>,
    enabled: Boolean,
    onSelect: (RatingScheme) -> Unit,
    modifier: Modifier = Modifier
) {
    var expanded by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(
        expanded = expanded && enabled,
        onExpandedChange = { if (enabled) expanded = it },
        modifier = modifier.fillMaxWidth()
    ) {
        OutlinedTextField(
            value = selected.label,
            onValueChange = {},
            readOnly = true,
            enabled = enabled,
            label = { Text(label) },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
            modifier = Modifier
                .menuAnchor()
                .fillMaxWidth()
        )
        ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            options.forEach { option ->
                DropdownMenuItem(
                    text = { Text(option.label) },
                    onClick = {
                        onSelect(option)
                        expanded = false
                    }
                )
            }
        }
    }
}

/** Primary action: Start while idle, a clear Stop while this run is active. */
@Composable
fun RunButton(
    startLabel: String,
    anyRunActive: Boolean,
    thisRunActive: Boolean,
    canStart: Boolean,
    onStart: () -> Unit,
    onStop: () -> Unit,
    modifier: Modifier = Modifier
) {
    val haptic = LocalHapticFeedback.current
    val buttonModifier = modifier
        .fillMaxWidth()
        .heightIn(min = 52.dp)

    if (thisRunActive) {
        FilledTonalButton(
            onClick = {
                haptic.performHapticFeedback(HapticFeedbackType.LongPress)
                onStop()
            },
            modifier = buttonModifier,
            colors = ButtonDefaults.filledTonalButtonColors(
                containerColor = MaterialTheme.colorScheme.errorContainer,
                contentColor = MaterialTheme.colorScheme.onErrorContainer
            )
        ) {
            Icon(Icons.Rounded.Stop, contentDescription = null, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(8.dp))
            Text("Stop")
        }
    } else {
        Button(
            onClick = {
                haptic.performHapticFeedback(HapticFeedbackType.LongPress)
                onStart()
            },
            enabled = canStart && !anyRunActive,
            modifier = buttonModifier
        ) {
            Text(if (anyRunActive) "Another run is in progress" else startLabel)
        }
    }
}

@Composable
fun RunProgress(
    processed: Int,
    total: Int,
    done: Int,
    skipped: Int,
    failed: Int,
    modifier: Modifier = Modifier
) {
    val progress = if (total > 0) processed.toFloat() / total.toFloat() else 0f
    Column(modifier = modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("$processed of $total", style = MaterialTheme.typography.titleSmall)
            Text(
                text = buildString {
                    append("$done done")
                    if (skipped > 0) append(" · $skipped already done")
                    if (failed > 0) append(" · $failed failed")
                },
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
        LinearProgressIndicator(progress = { progress }, modifier = Modifier.fillMaxWidth())
    }
}

@Composable
fun EmptyState(title: String, body: String, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 24.dp, vertical = 32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        Text(title, style = MaterialTheme.typography.titleMedium, textAlign = TextAlign.Center)
        Text(
            body,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center
        )
    }
}
