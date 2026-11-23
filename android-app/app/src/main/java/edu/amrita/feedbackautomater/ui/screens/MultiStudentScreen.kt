package edu.amrita.feedbackautomater.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import edu.amrita.feedbackautomater.model.FeedbackMode
import edu.amrita.feedbackautomater.model.ItemStatus
import edu.amrita.feedbackautomater.model.RatingScheme
import edu.amrita.feedbackautomater.ui.ActiveRunType
import edu.amrita.feedbackautomater.ui.MainUiState
import edu.amrita.feedbackautomater.ui.MainViewModel
import edu.amrita.feedbackautomater.ui.components.EmptyState
import edu.amrita.feedbackautomater.ui.components.RatingDropdown
import edu.amrita.feedbackautomater.ui.components.RunButton
import edu.amrita.feedbackautomater.ui.components.RunProgress
import edu.amrita.feedbackautomater.ui.components.StatusIcon

@Composable
fun MultiStudentScreen(state: MainUiState, vm: MainViewModel, modifier: Modifier = Modifier) {
    Column(modifier = modifier.fillMaxSize()) {
        // Tabs stay tappable during a run so progress on either list can always be inspected.
        TabRow(selectedTabIndex = state.multiTabIndex) {
            Tab(
                selected = state.multiTabIndex == 0,
                onClick = { vm.setMultiTabIndex(0) },
                text = { Text(if (state.queueItems.isEmpty()) "MyAmrita queue" else "MyAmrita queue (${state.queueItems.size})") }
            )
            Tab(
                selected = state.multiTabIndex == 1,
                onClick = { vm.setMultiTabIndex(1) },
                text = { Text(if (state.batchItems.isEmpty()) "AmritaVidya batch" else "AmritaVidya batch (${state.batchItems.size})") }
            )
        }
        if (state.multiTabIndex == 0) QueuePane(state, vm) else BatchPane(state, vm)
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun QueuePane(state: MainUiState, vm: MainViewModel) {
    var mode by rememberSaveable { mutableStateOf(FeedbackMode.BOTH) }
    var rating by rememberSaveable { mutableStateOf(RatingScheme.VERY_GOOD) }
    var pasted by rememberSaveable { mutableStateOf("") }
    val running = state.isRunning
    val items = state.queueItems

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item(key = "mode") {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(FeedbackMode.BOTH, FeedbackMode.COURSE, FeedbackMode.TLP).forEach { m ->
                    FilterChip(
                        selected = mode == m,
                        onClick = { mode = m },
                        enabled = !running,
                        label = {
                            Text(
                                when (m) {
                                    FeedbackMode.BOTH -> "Course + TLP"
                                    FeedbackMode.COURSE -> "Course"
                                    else -> "TLP"
                                }
                            )
                        }
                    )
                }
            }
        }
        item(key = "input") {
            OutlinedTextField(
                value = pasted,
                onValueChange = { pasted = it },
                label = { Text("Students") },
                supportingText = { Text("One per line: roll number or email, then a comma, then the password") },
                minLines = 3,
                maxLines = 6,
                enabled = !running,
                modifier = Modifier.fillMaxWidth()
            )
        }
        item(key = "rating") {
            RatingDropdown(
                label = "Rating for these students",
                selected = rating,
                options = RatingScheme.singleOptions,
                enabled = !running,
                onSelect = { rating = it }
            )
        }
        item(key = "add") {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilledTonalButton(
                    onClick = {
                        vm.addBulkQueueStudents(pasted, mode, rating)
                        pasted = ""
                    },
                    enabled = !running && pasted.isNotBlank()
                ) { Text("Add to queue") }
                TextButton(
                    onClick = { vm.clearQueue() },
                    enabled = !running && items.isNotEmpty()
                ) { Text("Clear all") }
            }
        }
        item(key = "run") {
            RunButton(
                startLabel = "Start queue",
                anyRunActive = running,
                thisRunActive = state.activeRunType == ActiveRunType.QUEUE,
                canStart = items.isNotEmpty(),
                onStart = { vm.startQueueRun() },
                onStop = { vm.cancelActiveRun() }
            )
        }

        if (items.isEmpty()) {
            item(key = "empty") {
                EmptyState(
                    title = "No students in the queue",
                    body = "Paste a few students above. They are processed one after another."
                )
            }
        } else {
            item(key = "progress") {
                RunProgress(
                    processed = items.count { it.status == ItemStatus.DONE || it.status == ItemStatus.FAILED },
                    total = items.size,
                    done = items.count { it.status == ItemStatus.DONE },
                    skipped = 0,
                    failed = items.count { it.status == ItemStatus.FAILED }
                )
            }
            item(key = "divider") { HorizontalDivider() }
            items(items, key = { it.id }) { item ->
                ListItem(
                    headlineContent = { Text(item.email, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                    supportingContent = {
                        Text(
                            "${item.mode.label} · ${item.rating.label}" +
                                if (item.status == ItemStatus.PENDING) "" else " · ${item.statusText}"
                        )
                    },
                    leadingContent = { StatusIcon(item.status) },
                    trailingContent = {
                        if (!running) {
                            IconButton(onClick = { vm.removeQueueItem(item.id) }) {
                                Icon(Icons.Rounded.Close, contentDescription = "Remove ${item.email}")
                            }
                        }
                    },
                    colors = ListItemDefaults.colors(containerColor = Color.Transparent)
                )
            }
        }
    }
}

@Composable
private fun BatchPane(state: MainUiState, vm: MainViewModel) {
    var prefix by rememberSaveable { mutableStateOf("bl.sc.u4aie24") }
    var start by rememberSaveable { mutableStateOf("101") }
    var end by rememberSaveable { mutableStateOf("160") }
    var pasted by rememberSaveable { mutableStateOf("") }
    val running = state.isRunning
    val items = state.batchItems

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item(key = "range_title") {
            Text("Add a roll number range", style = MaterialTheme.typography.titleMedium)
        }
        item(key = "range") {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = prefix,
                    onValueChange = { prefix = it },
                    label = { Text("Prefix") },
                    singleLine = true,
                    enabled = !running,
                    modifier = Modifier.weight(1.7f)
                )
                OutlinedTextField(
                    value = start,
                    onValueChange = { start = it.filter(Char::isDigit) },
                    label = { Text("From") },
                    singleLine = true,
                    enabled = !running,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.weight(1f)
                )
                OutlinedTextField(
                    value = end,
                    onValueChange = { end = it.filter(Char::isDigit) },
                    label = { Text("To") },
                    singleLine = true,
                    enabled = !running,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.weight(1f)
                )
            }
        }
        item(key = "default_pass") {
            OutlinedTextField(
                value = state.batchDefaultPassword,
                onValueChange = { vm.updateBatchSettings(defaultPass = it) },
                label = { Text("Default password") },
                singleLine = true,
                enabled = !running,
                modifier = Modifier.fillMaxWidth()
            )
        }
        item(key = "range_actions") {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilledTonalButton(
                    onClick = { vm.addBatchRange(prefix, start, end) },
                    enabled = !running
                ) { Text("Add range") }
                TextButton(
                    onClick = { vm.clearBatch() },
                    enabled = !running && items.isNotEmpty()
                ) { Text("Clear all") }
            }
        }
        item(key = "paste") {
            OutlinedTextField(
                value = pasted,
                onValueChange = { pasted = it },
                label = { Text("Or paste a list") },
                supportingText = { Text("Roll numbers or emails, one per line. Add ,password to override the default.") },
                minLines = 2,
                maxLines = 5,
                enabled = !running,
                modifier = Modifier.fillMaxWidth()
            )
        }
        if (pasted.isNotBlank()) {
            item(key = "paste_add") {
                FilledTonalButton(
                    onClick = {
                        vm.addBulkBatchStudents(pasted)
                        pasted = ""
                    },
                    enabled = !running
                ) { Text("Add pasted list") }
            }
        }
        item(key = "rating") {
            RatingDropdown(
                label = "Rating scheme",
                selected = state.batchRating,
                options = RatingScheme.batchOptions,
                enabled = !running,
                onSelect = { vm.updateBatchSettings(rating = it) }
            )
        }
        item(key = "run") {
            RunButton(
                startLabel = "Start batch",
                anyRunActive = running,
                thisRunActive = state.activeRunType == ActiveRunType.BATCH,
                canStart = items.isNotEmpty(),
                onStart = { vm.startBatchRun() },
                onStop = { vm.cancelActiveRun() }
            )
        }

        if (items.isEmpty()) {
            item(key = "empty") {
                EmptyState(
                    title = "No roll numbers yet",
                    body = "Add a range to queue a whole class in one go."
                )
            }
        } else {
            val done = items.count { it.status == ItemStatus.DONE }
            val skipped = items.count { it.status == ItemStatus.SKIPPED }
            val failed = items.count { it.status == ItemStatus.FAILED }
            item(key = "progress") {
                RunProgress(
                    processed = done + skipped + failed,
                    total = items.size,
                    done = done,
                    skipped = skipped,
                    failed = failed
                )
            }
            item(key = "divider") { HorizontalDivider() }
            items(items, key = { it.id }) { student ->
                ListItem(
                    headlineContent = { Text(student.username, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                    supportingContent = {
                        val detail = listOf(student.studentName, if (student.status == ItemStatus.PENDING) "" else student.statusText)
                            .filter { it.isNotBlank() }
                            .joinToString(" · ")
                        if (detail.isNotBlank()) Text(detail, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    },
                    leadingContent = { StatusIcon(student.status) },
                    trailingContent = {
                        if (!running) {
                            IconButton(onClick = { vm.removeBatchItem(student.id) }) {
                                Icon(Icons.Rounded.Close, contentDescription = "Remove ${student.username}")
                            }
                        }
                    },
                    colors = ListItemDefaults.colors(containerColor = Color.Transparent)
                )
            }
        }
    }
}
