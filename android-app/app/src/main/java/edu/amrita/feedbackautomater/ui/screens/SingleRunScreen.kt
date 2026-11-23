package edu.amrita.feedbackautomater.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Visibility
import androidx.compose.material.icons.rounded.VisibilityOff
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import edu.amrita.feedbackautomater.model.FeedbackMode
import edu.amrita.feedbackautomater.model.RatingScheme
import edu.amrita.feedbackautomater.ui.ActiveRunType
import edu.amrita.feedbackautomater.ui.MainUiState
import edu.amrita.feedbackautomater.ui.MainViewModel
import edu.amrita.feedbackautomater.ui.components.RatingDropdown
import edu.amrita.feedbackautomater.ui.components.RunButton
import edu.amrita.feedbackautomater.ui.components.StatusIcon
import edu.amrita.feedbackautomater.ui.components.statusLabel

private fun portalChipLabel(mode: FeedbackMode) = when (mode) {
    FeedbackMode.TLP -> "TLP"
    FeedbackMode.COURSE -> "Course"
    FeedbackMode.BOTH -> "Course + TLP"
    FeedbackMode.VIDYA -> "AmritaVidya"
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun SingleRunScreen(state: MainUiState, vm: MainViewModel, modifier: Modifier = Modifier) {
    val isVidya = state.mode == FeedbackMode.VIDYA
    val running = state.isRunning
    var showPassword by rememberSaveable { mutableStateOf(false) }

    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        item(key = "portal") {
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                FeedbackMode.entries.forEach { mode ->
                    FilterChip(
                        selected = state.mode == mode,
                        onClick = { vm.setMode(mode) },
                        enabled = !running,
                        label = { Text(portalChipLabel(mode)) }
                    )
                }
            }
        }

        item(key = "form") {
            androidx.compose.foundation.layout.Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(
                    value = state.emailOrUsername,
                    onValueChange = { vm.updateSingleCredentials(email = it) },
                    label = { Text(if (isVidya) "Roll number" else "Amrita email or roll number") },
                    supportingText = {
                        Text(
                            if (isVidya) "Pasting your Amrita email works too. Only the roll number is used."
                            else "A roll number is completed to @bl.students.amrita.edu."
                        )
                    },
                    singleLine = true,
                    enabled = !running,
                    keyboardOptions = KeyboardOptions(
                        keyboardType = KeyboardType.Email,
                        imeAction = ImeAction.Next
                    ),
                    modifier = Modifier.fillMaxWidth()
                )

                OutlinedTextField(
                    value = state.password,
                    onValueChange = { vm.updateSingleCredentials(password = it) },
                    label = { Text(if (isVidya) "Password (blank uses default)" else "Password") },
                    singleLine = true,
                    enabled = !running,
                    visualTransformation = if (showPassword) VisualTransformation.None else PasswordVisualTransformation(),
                    trailingIcon = {
                        IconButton(onClick = { showPassword = !showPassword }) {
                            Icon(
                                imageVector = if (showPassword) Icons.Rounded.VisibilityOff else Icons.Rounded.Visibility,
                                contentDescription = if (showPassword) "Hide password" else "Show password"
                            )
                        }
                    },
                    keyboardOptions = KeyboardOptions(
                        keyboardType = KeyboardType.Password,
                        imeAction = ImeAction.Done
                    ),
                    modifier = Modifier.fillMaxWidth()
                )

                RatingDropdown(
                    label = "Rating for every question",
                    selected = state.selectedRating,
                    options = if (isVidya) RatingScheme.batchOptions else RatingScheme.singleOptions,
                    enabled = !running,
                    onSelect = { vm.updateSingleCredentials(rating = it) }
                )
            }
        }

        item(key = "action") {
            androidx.compose.foundation.layout.Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                RunButton(
                    startLabel = "Submit all pending feedback",
                    anyRunActive = running,
                    thisRunActive = state.activeRunType == ActiveRunType.SINGLE,
                    canStart = state.emailOrUsername.isNotBlank() && (isVidya || state.password.isNotBlank()),
                    onStart = { vm.startSingleRun() },
                    onStop = { vm.cancelActiveRun() }
                )
                Text(
                    text = "Your password is used on this phone only and is never stored.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }

        if (state.subjects.isNotEmpty()) {
            item(key = "subjects_title") {
                Text("Subjects found", style = MaterialTheme.typography.titleMedium)
            }
            items(state.subjects, key = { it.info }) { subject ->
                ListItem(
                    headlineContent = {
                        Text(subject.info, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    },
                    supportingContent = { Text(statusLabel(subject.status)) },
                    leadingContent = { StatusIcon(subject.status) },
                    colors = ListItemDefaults.colors(containerColor = Color.Transparent),
                    modifier = Modifier.fillMaxWidth()
                )
            }
        }
    }
}
