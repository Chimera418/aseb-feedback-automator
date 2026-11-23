package edu.amrita.feedbackautomater.engine

import edu.amrita.feedbackautomater.model.BatchStudentItem
import edu.amrita.feedbackautomater.model.ItemStatus
import edu.amrita.feedbackautomater.model.LogLevel
import edu.amrita.feedbackautomater.model.PendingSubject
import edu.amrita.feedbackautomater.model.RatingScheme
import edu.amrita.feedbackautomater.model.normalizeVidyaRoll
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.withContext
import okhttp3.Cookie
import okhttp3.CookieJar
import okhttp3.FormBody
import okhttp3.HttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import org.jsoup.Jsoup
import java.net.URI
import java.util.concurrent.TimeUnit

/**
 * Pure client-side HTTP engine for AmritaVidya.
 * Runs directly on the user's device network with clean per-student session isolation.
 */
class VidyaHttpEngine(
    private val onLog: (String, LogLevel) -> Unit
) {
    companion object {
        private const val PRIMARY_HOST = "web-blr.amrita.edu"
        private const val FALLBACK_HOST = "210.212.205.26"
        private const val BASE_URL = "http://$PRIMARY_HOST/amritavidya/"
    }

    private class MemoryCookieJar : CookieJar {
        private val store = mutableMapOf<String, MutableList<Cookie>>()

        override fun saveFromResponse(url: HttpUrl, cookies: List<Cookie>) {
            val hostCookies = store.getOrPut(url.host) { mutableListOf() }
            for (c in cookies) {
                hostCookies.removeAll { it.name == c.name && it.path == c.path }
                hostCookies.add(c)
            }
        }

        override fun loadForRequest(url: HttpUrl): List<Cookie> {
            return store[url.host]?.filter { it.expiresAt >= System.currentTimeMillis() } ?: emptyList()
        }
    }

    private fun newClient(): OkHttpClient = OkHttpClient.Builder()
        .cookieJar(MemoryCookieJar())
        .followRedirects(true)
        .followSslRedirects(true)
        .connectTimeout(25, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    private fun resolveUrl(baseUrl: String, relativeOrAbsolute: String): String {
        return try {
            URI(baseUrl).resolve(relativeOrAbsolute).toString()
        } catch (_: Exception) {
            baseUrl + relativeOrAbsolute.trimStart('/')
        }
    }

    private fun fetchWithFallback(client: OkHttpClient, url: String): Pair<String, String> {
        var currentUrl = url
        var lastError: Exception? = null
        for (attempt in 1..3) {
            try {
                val req = Request.Builder()
                    .url(currentUrl)
                    .header("User-Agent", "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36")
                    .get()
                    .build()
                client.newCall(req).execute().use { resp ->
                    val body = resp.body?.string().orEmpty()
                    return currentUrl to body
                }
            } catch (e: Exception) {
                lastError = e
                onLog("Network retry $attempt/3 connecting to AmritaVidya...", LogLevel.WARN)
                if (attempt == 1) {
                    currentUrl = when {
                        PRIMARY_HOST in currentUrl -> currentUrl.replace(PRIMARY_HOST, FALLBACK_HOST)
                        FALLBACK_HOST in currentUrl -> currentUrl.replace(FALLBACK_HOST, PRIMARY_HOST)
                        else -> currentUrl
                    }
                }
                Thread.sleep(1500)
            }
        }
        throw RuntimeException("Could not reach AmritaVidya portal: ${lastError?.message}")
    }

    private fun login(client: OkHttpClient, rawUsername: String, password: String): Pair<String, String> {
        val username = normalizeVidyaRoll(rawUsername)
        val loginUrl = BASE_URL + "main_login.php"
        val (resolvedLoginUrl, loginHtml) = fetchWithFallback(client, loginUrl)
        val activeBase = resolvedLoginUrl.substringBeforeLast("/") + "/"
        val loginDoc = Jsoup.parse(loginHtml, resolvedLoginUrl)
        val form = loginDoc.selectFirst("form")
        val actionUrl = form?.absUrl("action")?.ifBlank { resolvedLoginUrl } ?: resolvedLoginUrl

        val formBuilder = FormBody.Builder()
        form?.select("input[type=hidden]")?.forEach { hidden ->
            val name = hidden.attr("name")
            if (name.isNotBlank()) formBuilder.add(name, hidden.attr("value"))
        }
        formBuilder.add("n1", username)
        formBuilder.add("n2", password)

        val postReq = Request.Builder()
            .url(actionUrl)
            .header("User-Agent", "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36")
            .header("Referer", resolvedLoginUrl)
            .post(formBuilder.build())
            .build()

        client.newCall(postReq).execute().use { resp ->
            val body = resp.body?.string().orEmpty()
            val lower = body.lowercase()
            val doc = Jsoup.parse(body)
            if ("invalid" in lower || "incorrect" in lower || doc.select("input[name=n2]").isNotEmpty()) {
                throw RuntimeException("Login failed for '$username' (wrong password?)")
            }
            val nameCandidate = doc.selectFirst("td b, table b, font b")?.text()?.trim()
                ?.takeIf { it.length in 2..60 }
                ?: "Student"
            return activeBase to nameCandidate
        }
    }

    private fun collectPending(client: OkHttpClient, baseUrl: String): List<PendingSubject> {
        val feedbackUrl = baseUrl + "feedback_home.php"
        val (_, html) = fetchWithFallback(client, feedbackUrl)
        val doc = Jsoup.parse(html, feedbackUrl)

        val pending = mutableListOf<PendingSubject>()
        for (row in doc.select("tr")) {
            val link = row.select("a").firstOrNull { it.text().contains("Enter Feedback", ignoreCase = true) }
                ?: continue
            val cells = row.select("td").map { it.text().trim() }
            val code = cells.getOrNull(1).orEmpty()
            val title = cells.getOrNull(2).orEmpty()
            val faculty = cells.getOrNull(3).orEmpty()
            val href = link.attr("href").trim()
            val url = if (href.isNotEmpty() && !href.startsWith("#") && !href.lowercase().startsWith("javascript:")) {
                resolveUrl(baseUrl, href)
            } else null

            pending.add(
                PendingSubject(
                    info = "$code $title | $faculty".trim(),
                    code = code,
                    url = url
                )
            )
        }
        return pending
    }

    private fun submitSingleForm(client: OkHttpClient, baseUrl: String, item: PendingSubject, scheme: RatingScheme) {
        val formUrl = item.url ?: throw RuntimeException("No form URL found for ${item.code}")
        val (resolvedUrl, html) = fetchWithFallback(client, formUrl)
        val doc = Jsoup.parse(html, resolvedUrl)
        val form = doc.selectFirst("form") ?: throw RuntimeException("No form found on ${item.code}")
        val actionUrl = form.absUrl("action").ifBlank { resolvedUrl }

        val formBuilder = FormBody.Builder()

        form.select("input").forEach { input ->
            val type = input.attr("type").lowercase()
            val name = input.attr("name")
            if (name.isBlank()) return@forEach
            if (type == "hidden" || type == "text") {
                formBuilder.add(name, input.attr("value"))
            }
        }
        form.select("textarea").forEach { ta ->
            val name = ta.attr("name")
            if (name.isNotBlank()) formBuilder.add(name, "")
        }

        val radioGroups = linkedMapOf<String, MutableList<String>>()
        for (radio in form.select("input[type=radio]")) {
            val name = radio.attr("name")
            if (name.isBlank()) continue
            radioGroups.getOrPut(name) { mutableListOf() }.add(radio.attr("value"))
        }

        if (radioGroups.isEmpty()) {
            throw RuntimeException("No radio questions found for ${item.code}")
        }

        for ((name, values) in radioGroups) {
            val chosenIdx = scheme.resolveIndex(values.size)
            formBuilder.add(name, values[chosenIdx])
        }

        form.selectFirst("input[type=submit], button[type=submit]")?.let { btn ->
            val name = btn.attr("name")
            if (name.isNotBlank()) formBuilder.add(name, btn.attr("value").ifBlank { "Submit" })
        }

        val req = Request.Builder()
            .url(actionUrl)
            .header("User-Agent", "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36")
            .header("Referer", resolvedUrl)
            .post(formBuilder.build())
            .build()

        client.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful && resp.code !in 300..399) {
                throw RuntimeException("HTTP ${resp.code} submitting ${item.code}")
            }
        }

        val remaining = collectPending(client, baseUrl)
        if (remaining.any { it.code == item.code }) {
            throw RuntimeException("${item.code} still pending after submission")
        }
    }

    suspend fun runSingle(
        username: String,
        password: String,
        ratingScheme: RatingScheme,
        onStudentName: (String) -> Unit = {},
        onSubjectsFetched: (List<PendingSubject>) -> Unit = {},
        onSubjectStatus: (String, ItemStatus) -> Unit = { _, _ -> }
    ): Triple<Int, Int, Int> = withContext(Dispatchers.IO) {
        val client = newClient()
        onLog("Logging in to AmritaVidya as $username...", LogLevel.INFO)
        val (activeBase, studentName) = login(client, username, password)
        onStudentName(studentName)
        onLog("Signed in as $studentName", LogLevel.SUCCESS)

        val pending = collectPending(client, activeBase)
        onSubjectsFetched(pending)
        onLog("Found ${pending.size} pending feedback(s).", LogLevel.INFO)

        if (pending.isEmpty()) {
            onLog("No pending feedbacks. You're all set!", LogLevel.SUCCESS)
            return@withContext Triple(0, 1, 0)
        }

        var done = 0
        var failed = 0
        for ((idx, item) in pending.withIndex()) {
            if (!isActive) throw CancellationException()
            onSubjectStatus(item.info, ItemStatus.PROCESSING)
            onLog("[${idx + 1}/${pending.size}] Submitting ${item.info}...", LogLevel.INFO)
            try {
                submitSingleForm(client, activeBase, item, ratingScheme)
                onSubjectStatus(item.info, ItemStatus.DONE)
                onLog("Submitted ${item.code}", LogLevel.SUCCESS)
                done++
            } catch (e: Exception) {
                onSubjectStatus(item.info, ItemStatus.FAILED)
                onLog("Failed ${item.code}: ${e.message}", LogLevel.ERROR)
                failed++
            }
        }
        onLog("AmritaVidya automation complete!", LogLevel.SUCCESS)
        Triple(done, 0, failed)
    }

    suspend fun runBatch(
        students: List<BatchStudentItem>,
        ratingScheme: RatingScheme,
        delaySeconds: Double,
        onProgress: (current: Int, total: Int, label: String) -> Unit = { _, _, _ -> },
        onUpdateStudent: (id: String, transform: (BatchStudentItem) -> BatchStudentItem) -> Unit
    ): Triple<Int, Int, Int> = withContext(Dispatchers.IO) {
        onLog("Starting AmritaVidya Batch for ${students.size} student(s)...", LogLevel.INFO)
        var doneCount = 0
        var skippedCount = 0
        var failedCount = 0

        for ((idx, student) in students.withIndex()) {
            if (!isActive) {
                onLog("Batch cancelled by user.", LogLevel.WARN)
                break
            }

            onProgress(idx + 1, students.size, "Processing ${student.username}")
            onUpdateStudent(student.id) {
                it.copy(status = ItemStatus.PROCESSING, statusText = "Logging in...")
            }

            val client = newClient()
            try {
                val (activeBase, name) = login(client, student.username, student.password)
                onUpdateStudent(student.id) {
                    it.copy(studentName = name, statusText = "Fetching...")
                }

                val pending = collectPending(client, activeBase)
                if (pending.isEmpty()) {
                    skippedCount++
                    onUpdateStudent(student.id) {
                        it.copy(pendingCount = 0, status = ItemStatus.SKIPPED, statusText = "Already Done")
                    }
                    onLog("[${idx + 1}/${students.size}] ${student.username} ($name): Already done.", LogLevel.INFO)
                } else {
                    var submitted = 0
                    for ((sIdx, item) in pending.withIndex()) {
                        if (!isActive) throw CancellationException()
                        onUpdateStudent(student.id) {
                            it.copy(
                                pendingCount = pending.size,
                                statusText = "Submitting ${sIdx + 1}/${pending.size}"
                            )
                        }
                        try {
                            submitSingleForm(client, activeBase, item, ratingScheme)
                            submitted++
                        } catch (e: Exception) {
                            onLog("${student.username} / ${item.code}: ${e.message}", LogLevel.WARN)
                        }
                    }
                    doneCount++
                    onUpdateStudent(student.id) {
                        it.copy(
                            status = ItemStatus.DONE,
                            statusText = "Done ($submitted/${pending.size})"
                        )
                    }
                    onLog("[${idx + 1}/${students.size}] ${student.username} ($name): $submitted/${pending.size} submitted.", LogLevel.SUCCESS)
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                failedCount++
                val shortErr = e.message?.lines()?.firstOrNull()?.take(45) ?: "Error"
                onUpdateStudent(student.id) {
                    it.copy(status = ItemStatus.FAILED, statusText = "Failed")
                }
                onLog("[${idx + 1}/${students.size}] ${student.username}: $shortErr", LogLevel.ERROR)
            }

            if (delaySeconds > 0 && idx < students.lastIndex && isActive) {
                delay((delaySeconds * 1000).toLong())
            }
        }
        onLog("Batch finished — Done: $doneCount, Skipped: $skippedCount, Failed: $failedCount", LogLevel.SUCCESS)
        Triple(doneCount, skippedCount, failedCount)
    }
}
