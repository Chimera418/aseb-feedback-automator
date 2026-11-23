package edu.amrita.feedbackautomater.util

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import edu.amrita.feedbackautomater.MainActivity
import edu.amrita.feedbackautomater.R

/**
 * Live progress (the foreground-service notification) and the finish notification.
 */
class AutomationNotificationHelper(private val context: Context) {

    companion object {
        private const val CHANNEL_PROGRESS = "amrita_automation_progress"
        private const val CHANNEL_DONE = "amrita_automation_done"
        const val PROGRESS_NOTIF_ID = 1001
        private const val COMPLETE_NOTIF_ID = 1002
    }

    init {
        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_PROGRESS, "Run progress", NotificationManager.IMPORTANCE_LOW).apply {
                description = "Shown while feedback is being submitted"
            }
        )
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_DONE, "Run finished", NotificationManager.IMPORTANCE_DEFAULT).apply {
                description = "Tells you when a run has finished"
            }
        )
    }

    private fun openAppIntent(): PendingIntent = PendingIntent.getActivity(
        context,
        0,
        Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
        },
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
    )

    private fun canNotify(): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED

    fun buildProgressNotification(title: String, detail: String, current: Int = 0, total: Int = 0): Notification {
        val builder = NotificationCompat.Builder(context, CHANNEL_PROGRESS)
            .setSmallIcon(R.drawable.ic_notif_art)
            .setContentTitle(title)
            .setContentText(detail)
            .setContentIntent(openAppIntent())
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setCategory(NotificationCompat.CATEGORY_PROGRESS)
            .setPriority(NotificationCompat.PRIORITY_LOW)
        if (total > 0) builder.setProgress(total, current, false) else builder.setProgress(0, 0, true)
        return builder.build()
    }

    /** Same id as the foreground-service notification, so this just updates it in place. */
    fun showProgress(title: String, detail: String, current: Int = 0, total: Int = 0) {
        if (!canNotify()) return
        try {
            NotificationManagerCompat.from(context)
                .notify(PROGRESS_NOTIF_ID, buildProgressNotification(title, detail, current, total))
        } catch (_: SecurityException) {
        }
    }

    fun showComplete(title: String, summary: String) {
        cancelProgress()
        if (!canNotify()) return
        val notification = NotificationCompat.Builder(context, CHANNEL_DONE)
            .setSmallIcon(R.drawable.ic_notif_art)
            .setContentTitle(title)
            .setContentText(summary)
            .setStyle(NotificationCompat.BigTextStyle().bigText(summary))
            .setContentIntent(openAppIntent())
            .setAutoCancel(true)
            .setCategory(NotificationCompat.CATEGORY_STATUS)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .build()
        try {
            NotificationManagerCompat.from(context).notify(COMPLETE_NOTIF_ID, notification)
        } catch (_: SecurityException) {
        }
    }

    fun cancelProgress() {
        NotificationManagerCompat.from(context).cancel(PROGRESS_NOTIF_ID)
    }
}
