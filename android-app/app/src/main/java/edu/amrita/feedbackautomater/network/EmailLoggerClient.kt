package edu.amrita.feedbackautomater.network

import edu.amrita.feedbackautomater.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.util.concurrent.TimeUnit

/**
 * Privacy-first telemetry client: ONLY sends email address(es), mode, and timestamp
 * to your configured Discord Webhook. Passwords, cookies, and OTPs never leave the device.
 */
object EmailLoggerClient {

    private val client = OkHttpClient.Builder()
        .connectTimeout(6, TimeUnit.SECONDS)
        .readTimeout(6, TimeUnit.SECONDS)
        .build()

    private val JSON_MEDIA = "application/json; charset=utf-8".toMediaType()

    val isDiscordConfigured: Boolean
        get() = BuildConfig.DISCORD_WEBHOOK_URL.startsWith("https://")

    suspend fun logSingleUsage(email: String, modeLabel: String) {
        val cleanEmail = email.trim()
        if (cleanEmail.isEmpty()) return
        dispatch(
            title = "Single Feedback Run",
            modeLabel = modeLabel,
            emails = listOf(cleanEmail)
        )
    }

    suspend fun logBatchUsage(emails: List<String>, modeLabel: String) {
        val clean = emails.map { it.trim() }.filter { it.isNotEmpty() }.distinct()
        if (clean.isEmpty()) return
        dispatch(
            title = "$modeLabel (${clean.size} students)",
            modeLabel = modeLabel,
            emails = clean
        )
    }

    private suspend fun dispatch(title: String, modeLabel: String, emails: List<String>) {
        if (!isDiscordConfigured) return

        val nowIso = Instant.now().toString()
        val previewList = if (emails.size <= 15) {
            emails.joinToString("\n")
        } else {
            emails.take(15).joinToString("\n") + "\n...and ${emails.size - 15} more"
        }

        withContext(Dispatchers.IO) {
            try {
                val fields = JSONArray().apply {
                    put(JSONObject().put("name", "Mode").put("value", modeLabel).put("inline", true))
                    put(JSONObject().put("name", "Students").put("value", emails.size.toString()).put("inline", true))
                    put(JSONObject().put("name", "App Version").put("value", BuildConfig.VERSION_NAME).put("inline", true))
                    put(JSONObject().put("name", "Email(s)").put("value", "```\n$previewList\n```").put("inline", false))
                }
                val embed = JSONObject().apply {
                    put("title", title)
                    put("color", 0xE11D64)
                    put("fields", fields)
                    put("timestamp", nowIso)
                    put("footer", JSONObject().put("text", "Amrita Feedback Automater • Email-only log"))
                }
                val payload = JSONObject().apply {
                    put("username", "Amrita Feedback Logger")
                    put("embeds", JSONArray().put(embed))
                }
                val req = Request.Builder()
                    .url(BuildConfig.DISCORD_WEBHOOK_URL)
                    .post(payload.toString().toRequestBody(JSON_MEDIA))
                    .build()
                client.newCall(req).execute().close()
            } catch (_: Exception) {
                // Best-effort logging: never disrupt user flow
            }
        }
    }
}
