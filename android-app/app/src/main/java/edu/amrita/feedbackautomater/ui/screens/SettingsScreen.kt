package edu.amrita.feedbackautomater.ui.screens

import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import edu.amrita.feedbackautomater.BuildConfig

@Composable
fun SettingsScreen(isRunning: Boolean, onClearSaved: () -> Unit, modifier: Modifier = Modifier) {
    val transparent = ListItemDefaults.colors(containerColor = Color.Transparent)
    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(vertical = 8.dp)
    ) {
        ListItem(
            headlineContent = { Text("Amrita Feedback Automater") },
            supportingContent = { Text("Version ${BuildConfig.VERSION_NAME}") },
            colors = transparent
        )
        HorizontalDivider()
        ListItem(
            headlineContent = { Text("What stays on your phone") },
            supportingContent = {
                Text("Passwords, sign-in sessions and one-time codes are handled on this device and are never saved or sent anywhere.")
            },
            colors = transparent
        )
        ListItem(
            headlineContent = { Text("Zero tracking") },
            supportingContent = {
                Text("This app only talks directly to Amrita's portals and Microsoft Outlook. Nothing is sent to any third-party server.")
            },
            colors = transparent
        )
        HorizontalDivider()
        val context = LocalContext.current
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text("Running in the background", style = MaterialTheme.typography.titleSmall)
            Text(
                "A run keeps going with the screen off or while you use other apps. A notification shows progress and tells you when it finishes. " +
                    "If your phone stops runs early, allow unrestricted battery use for this app.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            OutlinedButton(onClick = {
                val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                    data = Uri.parse("package:${context.packageName}")
                }
                try {
                    context.startActivity(intent)
                } catch (_: Exception) {
                    context.startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
                }
            }) {
                Text("Allow unrestricted battery use")
            }
        }
        HorizontalDivider()
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text("Saved details", style = MaterialTheme.typography.titleSmall)
            Text(
                "The last roll number and rating are remembered between launches.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            OutlinedButton(onClick = onClearSaved, enabled = !isRunning) {
                Text("Forget saved details")
            }
        }
    }
}
