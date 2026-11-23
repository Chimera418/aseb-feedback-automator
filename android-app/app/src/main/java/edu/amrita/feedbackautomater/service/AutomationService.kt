package edu.amrita.feedbackautomater.service

import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.content.ContextCompat
import edu.amrita.feedbackautomater.util.AutomationNotificationHelper

/**
 * Keeps the process alive and the CPU awake while a run is in progress, so a run
 * continues with the screen off or the app in the background.
 * The actual work still happens in MainViewModel's app-level scope.
 */
class AutomationService : Service() {

    private var wakeLock: PowerManager.WakeLock? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val helper = AutomationNotificationHelper(applicationContext)
        val notification = helper.buildProgressNotification(
            title = "Amrita Feedback Automater",
            detail = "Submitting feedback in the background"
        )
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                AutomationNotificationHelper.PROGRESS_NOTIF_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
            )
        } else {
            startForeground(AutomationNotificationHelper.PROGRESS_NOTIF_ID, notification)
        }

        if (wakeLock == null) {
            val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
            wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "AmritaFeedback:run").apply {
                setReferenceCounted(false)
                acquire(5 * 60 * 60 * 1000L) // safety cap: 5 hours
            }
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        wakeLock?.let { if (it.isHeld) it.release() }
        wakeLock = null
        super.onDestroy()
    }

    companion object {
        fun start(context: Context) {
            ContextCompat.startForegroundService(context, Intent(context, AutomationService::class.java))
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, AutomationService::class.java))
        }
    }
}
