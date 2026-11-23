package edu.amrita.feedbackautomater

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.Groups
import androidx.compose.material.icons.rounded.History
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.TextButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarResult
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.core.content.ContextCompat
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.lifecycle.viewmodel.compose.viewModel
import edu.amrita.feedbackautomater.ui.MainViewModel
import edu.amrita.feedbackautomater.ui.screens.ActivityLogScreen
import edu.amrita.feedbackautomater.ui.screens.MultiStudentScreen
import edu.amrita.feedbackautomater.ui.screens.SettingsScreen
import edu.amrita.feedbackautomater.ui.screens.SingleRunScreen
import edu.amrita.feedbackautomater.ui.theme.AmritaTheme

class MainActivity : ComponentActivity() {

    private val requestNotifPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { /* optional */ }

    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
            != PackageManager.PERMISSION_GRANTED
        ) {
            requestNotifPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }

        setContent {
            AmritaTheme {
                AppShell(
                    onKeepScreenAwake = { keepAwake ->
                        if (keepAwake) window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                        else window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                    }
                )
            }
        }
    }
}

private enum class Tab(val title: String, val label: String) {
    RUN("Submit feedback", "Run"),
    QUEUE("Queue and batch", "Queue"),
    ACTIVITY("Activity", "Activity")
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AppShell(onKeepScreenAwake: (Boolean) -> Unit, vm: MainViewModel = viewModel()) {
    val state by vm.uiState.collectAsState()
    var selectedTab by rememberSaveable { mutableIntStateOf(0) }
    var showSettings by rememberSaveable { mutableStateOf(false) }
    val snackbarHost = remember { SnackbarHostState() }
    val haptic = LocalHapticFeedback.current
    val tab = Tab.entries[selectedTab]

    BackHandler(enabled = showSettings) { showSettings = false }

    DisposableEffect(Unit) { onDispose { } }

    // Finish popup (the system notification is posted by the ViewModel as well)
    state.completionSummary?.let { summary ->
        LaunchedEffect(summary) { haptic.performHapticFeedback(HapticFeedbackType.LongPress) }
        AlertDialog(
            onDismissRequest = { vm.dismissCompletionSummary() },
            title = { Text(summary.title) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(summary.subtitle)
                    Text("Done: ${summary.doneCount}")
                    Text("Already done: ${summary.skippedCount}")
                    Text("Failed: ${summary.failedCount}")
                }
            },
            confirmButton = {
                TextButton(onClick = { vm.dismissCompletionSummary() }) { Text("Close") }
            },
            dismissButton = {
                TextButton(onClick = {
                    vm.dismissCompletionSummary()
                    showSettings = false
                    selectedTab = Tab.ACTIVITY.ordinal
                }) { Text("View logs") }
            }
        )
    }

    Scaffold(
        topBar = {
            Column {
                TopAppBar(
                    title = { Text(if (showSettings) "About" else tab.title) },
                    navigationIcon = {
                        if (showSettings) {
                            IconButton(onClick = { showSettings = false }) {
                                Icon(Icons.AutoMirrored.Rounded.ArrowBack, contentDescription = "Back")
                            }
                        }
                    },
                    actions = {
                        if (!showSettings) {
                            IconButton(onClick = { showSettings = true }) {
                                Icon(Icons.Rounded.Settings, contentDescription = "About and privacy")
                            }
                        }
                    }
                )
                if (state.isRunning) {
                    LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                }
            }
        },
        bottomBar = {
            NavigationBar {
                NavigationBarItem(
                    selected = !showSettings && tab == Tab.RUN,
                    onClick = { showSettings = false; selectedTab = Tab.RUN.ordinal },
                    icon = { Icon(Icons.Rounded.PlayArrow, contentDescription = null) },
                    label = { Text(Tab.RUN.label) }
                )
                NavigationBarItem(
                    selected = !showSettings && tab == Tab.QUEUE,
                    onClick = { showSettings = false; selectedTab = Tab.QUEUE.ordinal },
                    icon = {
                        val queued = state.queueItems.size + state.batchItems.size
                        BadgedBox(badge = { if (queued > 0) Badge { Text(queued.coerceAtMost(99).toString()) } }) {
                            Icon(Icons.Rounded.Groups, contentDescription = null)
                        }
                    },
                    label = { Text(Tab.QUEUE.label) }
                )
                NavigationBarItem(
                    selected = !showSettings && tab == Tab.ACTIVITY,
                    onClick = { showSettings = false; selectedTab = Tab.ACTIVITY.ordinal },
                    icon = {
                        BadgedBox(badge = { if (state.isRunning) Badge() }) {
                            Icon(Icons.Rounded.History, contentDescription = null)
                        }
                    },
                    label = { Text(Tab.ACTIVITY.label) }
                )
            }
        },
        snackbarHost = { SnackbarHost(snackbarHost) }
    ) { innerPadding ->
        Surface(modifier = Modifier.fillMaxSize().padding(innerPadding)) {
            when {
                showSettings -> SettingsScreen(
                    isRunning = state.isRunning,
                    onClearSaved = { vm.clearSavedPreferences() }
                )
                tab == Tab.RUN -> SingleRunScreen(state, vm)
                tab == Tab.QUEUE -> MultiStudentScreen(state, vm)
                else -> ActivityLogScreen(state, vm)
            }
        }
    }
}
