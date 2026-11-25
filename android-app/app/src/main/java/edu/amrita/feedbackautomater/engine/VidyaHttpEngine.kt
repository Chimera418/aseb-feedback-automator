package edu.amrita.feedbackautomater.engine

import android.content.Context
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
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONArray
import org.json.JSONObject
import org.jsoup.Jsoup
import java.net.URI
import java.util.concurrent.TimeUnit

/**
 * Client-side engine for AmritaVidya.
 * Uses fast native HTTP first (with proper post-redirect URL tracking) and automatically
 * falls back to headless Android WebView if the portal requires JS onsubmit/onclick execution.
 */
class VidyaHttpEngine(
    private val context: Context,
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
        val encoded = relativeOrAbsolute.trim().replace(" ", "%20")
        return try {
            URI(baseUrl).resolve(encoded).toString()
        } catch (_: Exception) {
            baseUrl + encoded.trimStart('/')
        }
    }

    /**
     * Fetches a URL and returns (finalRedirectedUrl, htmlBody).
     * Returning resp.request.url ensures relative/empty form actions POST to the real target page.
     */
    private fun fetchWithFallback(client: OkHttpClient, url: String): Pair<String, String> {
        var currentUrl = url.replace(" ", "%20")
        var lastError: Exception? = null
        for (attempt in 1..3) {
            try {
                val req = Request.Builder()
                    .url(currentUrl)
                    .header("User-Agent", "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36")
                    .get()
                    .build()
                client.newCall(req).execute().use { resp ->
                    val finalUrl = resp.request.url.toString()
                    val body = resp.body?.string().orEmpty()
                    return finalUrl to body
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

    private fun submitSingleFormHttp(client: OkHttpClient, baseUrl: String, item: PendingSubject, scheme: RatingScheme) {
        val formUrl = item.url ?: throw RuntimeException("No form URL found for ${item.code}")
        val (resolvedUrl, html) = fetchWithFallback(client, formUrl)
        val doc = Jsoup.parse(html, resolvedUrl)

        // Pick the form that actually contains radio buttons (fallback to first form)
        val form = doc.select("form").firstOrNull { it.select("input[type=radio]").isNotEmpty() }
            ?: doc.selectFirst("form")
            ?: throw RuntimeException("No form found on ${item.code}")

        // Collect inputs from form (or full document if legacy malformed HTML split form/table)
        val scope = if (form.select("input[type=radio]").isNotEmpty()) form else doc

        // Match vidya.py: use the LAST submit button (submit / button / image)
        val submitBtn = scope.select("input[type=submit], button[type=submit], button:not([type]), input[type=image]").lastOrNull()

        // AmritaVidya sets form action dynamically via submit button onclick="this.form.action='feedback_submit_ver1.php';"
        val onclickAction = submitBtn?.attr("onclick")?.let { js ->
            Regex("""action\s*=\s*['"]([^'"]+)['"]""", RegexOption.IGNORE_CASE)
                .find(js)?.groupValues?.getOrNull(1)?.trim()
        }
        val rawAction = onclickAction?.takeIf { it.isNotEmpty() } ?: form.attr("action").trim()
        val actionUrl = if (rawAction.isNotEmpty()) {
            resolveUrl(baseUrl, rawAction)
        } else {
            resolvedUrl
        }
        val method = form.attr("method").trim().lowercase().ifEmpty { "post" }

        val fields = mutableListOf<Pair<String, String>>()

        scope.select("input").forEach { input ->
            val type = input.attr("type").trim().lowercase()
            val name = input.attr("name").trim()
            if (name.isBlank()) return@forEach
            when (type) {
                "hidden", "text", "", "number", "email" -> fields.add(name to input.attr("value"))
                "checkbox" -> if (input.hasAttr("checked")) fields.add(name to input.attr("value").ifBlank { "on" })
            }
        }
        scope.select("select").forEach { sel ->
            val name = sel.attr("name").trim()
            if (name.isBlank()) return@forEach
            val selectedOpt = sel.selectFirst("option[selected]") ?: sel.selectFirst("option")
            if (selectedOpt != null) {
                fields.add(name to selectedOpt.attr("value").ifBlank { selectedOpt.text() })
            }
        }
        scope.select("textarea").forEach { ta ->
            val name = ta.attr("name").trim()
            if (name.isNotBlank()) fields.add(name to ta.text())
        }

        val radioGroups = linkedMapOf<String, MutableList<String>>()
        for (radio in scope.select("input[type=radio]")) {
            val name = radio.attr("name").trim()
            if (name.isBlank()) continue
            radioGroups.getOrPut(name) { mutableListOf() }.add(radio.attr("value"))
        }

        if (radioGroups.isEmpty()) {
            throw RuntimeException("No radio questions found for ${item.code}")
        }

        for ((name, values) in radioGroups) {
            val chosenIdx = scheme.resolveIndex(values.size)
            fields.add(name to values[chosenIdx])
        }

        // Include submit button name/value if present
        if (submitBtn != null) {
            val btnName = submitBtn.attr("name").trim()
            val btnType = submitBtn.attr("type").trim().lowercase()
            if (btnName.isNotBlank()) {
                if (btnType == "image") {
                    fields.add("$btnName.x" to "10")
                    fields.add("$btnName.y" to "10")
                } else {
                    fields.add(btnName to submitBtn.attr("value").ifBlank { "Submit" })
                }
            }
        }

        val req = if (method == "get") {
            val httpUrlBuilder = (actionUrl.toHttpUrlOrNull()
                ?: throw RuntimeException("Invalid action URL: $actionUrl")).newBuilder()
            fields.forEach { (k, v) -> httpUrlBuilder.addQueryParameter(k, v) }
            Request.Builder()
                .url(httpUrlBuilder.build())
                .header("User-Agent", "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36")
                .header("Referer", resolvedUrl)
                .get()
                .build()
        } else {
            val formBuilder = FormBody.Builder()
            fields.forEach { (k, v) -> formBuilder.add(k, v) }
            Request.Builder()
                .url(actionUrl)
                .header("User-Agent", "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36")
                .header("Referer", resolvedUrl)
                .post(formBuilder.build())
                .build()
        }

        client.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful && resp.code !in 300..399) {
                throw RuntimeException("HTTP ${resp.code} submitting ${item.code}")
            }
        }

        val remaining = collectPending(client, baseUrl)
        if (remaining.any { it.code == item.code }) {
            throw RuntimeException("${item.code} still pending after HTTP submission")
        }
    }

    /**
     * Full Chromium WebView fallback for AmritaVidya (mirrors vidya.py Playwright behavior 1:1).
     * Handles JS onclick/onsubmit validation, alert/confirm dialogs, and quirky legacy PHP forms.
     */
    private suspend fun submitRemainingViaWebView(
        rawUsername: String,
        password: String,
        items: List<PendingSubject>,
        scheme: RatingScheme,
        onItemStatus: (PendingSubject, ItemStatus) -> Unit = { _, _ -> }
    ): Pair<Int, Int> {
        val username = normalizeVidyaRoll(rawUsername)
        val wv = withContext(Dispatchers.Main) { WebViewController(context) }
        var submitted = 0
        var failed = 0
        try {
            wv.clearAllCookies()
            var activeBase = BASE_URL
            wv.loadUrl(activeBase + "main_login.php")
            if (!wv.waitForSelector("input[name='n1']", 10_000L)) {
                activeBase = "http://$FALLBACK_HOST/amritavidya/"
                wv.loadUrl(activeBase + "main_login.php")
                if (!wv.waitForSelector("input[name='n1']", 12_000L)) {
                    throw RuntimeException("AmritaVidya login form did not load in WebView.")
                }
            }

            wv.fillInput("input[name='n1']", username)
            wv.fillInput("input[name='n2']", password)
            wv.clickSelector("input[type='image'], input[type='submit'], button[type='submit']")
            delay(2000)

            for (item in items) {
                onItemStatus(item, ItemStatus.PROCESSING)
                try {
                    val targetUrl = item.url?.replace(" ", "%20")
                    if (targetUrl != null) {
                        wv.loadUrl(targetUrl)
                    } else {
                        wv.loadUrl(activeBase + "feedback_home.php")
                        val codeJson = JSONObject.quote(item.code)
                        wv.evalJs(
                            """
                            (function() {
                                const rows = Array.from(document.querySelectorAll('tr'));
                                for (const r of rows) {
                                    if ((r.innerText || '').includes($codeJson)) {
                                        const a = Array.from(r.querySelectorAll('a')).find(el =>
                                            (el.innerText || '').toLowerCase().includes('enter feedback')
                                        );
                                        if (a) { a.click(); return '1'; }
                                    }
                                }
                                return '0';
                            })()
                            """.trimIndent()
                        )
                        delay(1500)
                    }

                    if (!wv.waitForSelector("input[type='radio']", 12_000L)) {
                        throw RuntimeException("No radio questions found for ${item.code}")
                    }

                    // Discover radio groups in DOM order
                    val groupsJson = wv.evalJs(
                        """
                        (function() {
                            const counts = {};
                            const order = [];
                            for (const r of document.querySelectorAll("input[type='radio']")) {
                                const n = r.name || '';
                                if (!(n in counts)) { counts[n] = 0; order.push(n); }
                                counts[n]++;
                            }
                            return JSON.stringify(order.map(n => ({ name: n, count: counts[n] })));
                        })()
                        """.trimIndent()
                    )
                    val arr = JSONArray(groupsJson.ifBlank { "[]" })
                    if (arr.length() == 0) throw RuntimeException("No radio groups found for ${item.code}")

                    // Build per-group chosen index map and check each radio
                    val picks = JSONObject()
                    for (i in 0 until arr.length()) {
                        val obj = arr.getJSONObject(i)
                        val name = obj.getString("name")
                        val count = obj.getInt("count")
                        picks.put(name, scheme.resolveIndex(count))
                    }
                    wv.evalJs(
                        """
                        (function() {
                            const picks = ${picks.toString()};
                            for (const [name, idx] of Object.entries(picks)) {
                                const radios = name
                                    ? Array.from(document.querySelectorAll("input[type='radio'][name='" + name.replace(/'/g, "\\'") + "']"))
                                    : Array.from(document.querySelectorAll("input[type='radio']"));
                                const target = radios[Math.min(idx, radios.length - 1)];
                                if (target) {
                                    target.checked = true;
                                    target.click();
                                    target.dispatchEvent(new Event('change', { bubbles: true }));
                                }
                            }
                            const btns = Array.from(document.querySelectorAll("input[type='submit'], button[type='submit'], input[type='image']"));
                            const submit = btns[btns.length - 1];
                            if (submit) {
                                submit.click();
                                return '1';
                            }
                            const f = document.querySelector('form');
                            if (f) { f.submit(); return '1'; }
                            return '0';
                        })()
                        """.trimIndent()
                    )
                    delay(1800)

                    // Verify cleared on feedback_home.php
                    wv.loadUrl(activeBase + "feedback_home.php")
                    val codeJson = JSONObject.quote(item.code)
                    val stillPending = wv.evalJs(
                        """
                        (function() {
                            const rows = Array.from(document.querySelectorAll('tr'));
                            for (const r of rows) {
                                if ((r.innerText || '').includes($codeJson)) {
                                    const hasLink = Array.from(r.querySelectorAll('a')).some(a =>
                                        (a.innerText || '').toLowerCase().includes('enter feedback')
                                    );
                                    if (hasLink) return '1';
                                }
                            }
                            return '0';
                        })()
                        """.trimIndent()
                    )
                    if (stillPending == "1") {
                        throw RuntimeException("${item.code} still pending after submission")
                    }
                    submitted++
                    onItemStatus(item, ItemStatus.DONE)
                    onLog("Submitted ${item.code}", LogLevel.SUCCESS)
                } catch (e: CancellationException) {
                    throw e
                } catch (e: Exception) {
                    failed++
                    onItemStatus(item, ItemStatus.FAILED)
                    onLog("Failed ${item.code}: ${e.message}", LogLevel.ERROR)
                }
            }
            return submitted to failed
        } finally {
            wv.destroy()
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
        onLog("Logging in to AmritaVidya as ${normalizeVidyaRoll(username)}...", LogLevel.INFO)
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
        var fallbackNeededFromIdx = -1

        for ((idx, item) in pending.withIndex()) {
            if (!isActive) throw CancellationException()
            onSubjectStatus(item.info, ItemStatus.PROCESSING)
            onLog("[${idx + 1}/${pending.size}] Submitting ${item.info}...", LogLevel.INFO)
            try {
                submitSingleFormHttp(client, activeBase, item, ratingScheme)
                onSubjectStatus(item.info, ItemStatus.DONE)
                onLog("Submitted ${item.code}", LogLevel.SUCCESS)
                done++
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                onLog("HTTP submit did not clear ${item.code}; switching to browser mode...", LogLevel.WARN)
                fallbackNeededFromIdx = idx
                break
            }
        }

        if (fallbackNeededFromIdx >= 0) {
            val remaining = pending.drop(fallbackNeededFromIdx)
            val (wvDone, wvFailed) = submitRemainingViaWebView(
                rawUsername = username,
                password = password,
                items = remaining,
                scheme = ratingScheme,
                onItemStatus = { item, status -> onSubjectStatus(item.info, status) }
            )
            done += wvDone
            failed += wvFailed
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
        var preferWebViewForSubmit = false

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
                    var fallbackFromIdx = if (preferWebViewForSubmit) 0 else -1

                    if (!preferWebViewForSubmit) {
                        for ((sIdx, item) in pending.withIndex()) {
                            if (!isActive) throw CancellationException()
                            onUpdateStudent(student.id) {
                                it.copy(
                                    pendingCount = pending.size,
                                    statusText = "Submitting ${sIdx + 1}/${pending.size}"
                                )
                            }
                            try {
                                submitSingleFormHttp(client, activeBase, item, ratingScheme)
                                submitted++
                            } catch (e: CancellationException) {
                                throw e
                            } catch (_: Exception) {
                                onLog("${student.username}: switching to browser submit for remaining ${pending.size - sIdx} form(s)...", LogLevel.WARN)
                                preferWebViewForSubmit = true
                                fallbackFromIdx = sIdx
                                break
                            }
                        }
                    }

                    if (fallbackFromIdx >= 0) {
                        val remaining = pending.drop(fallbackFromIdx)
                        var currentIdx = fallbackFromIdx
                        val (wvDone, _) = submitRemainingViaWebView(
                            rawUsername = student.username,
                            password = student.password,
                            items = remaining,
                            scheme = ratingScheme,
                            onItemStatus = { _, st ->
                                if (st == ItemStatus.PROCESSING) {
                                    currentIdx++
                                    onUpdateStudent(student.id) {
                                        it.copy(
                                            pendingCount = pending.size,
                                            statusText = "Submitting $currentIdx/${pending.size}"
                                        )
                                    }
                                }
                            }
                        )
                        submitted += wvDone
                    }

                    if (submitted > 0) {
                        doneCount++
                        onUpdateStudent(student.id) {
                            it.copy(
                                status = ItemStatus.DONE,
                                statusText = "Done ($submitted/${pending.size})"
                            )
                        }
                        onLog("[${idx + 1}/${students.size}] ${student.username} ($name): $submitted/${pending.size} submitted.", LogLevel.SUCCESS)
                    } else {
                        failedCount++
                        onUpdateStudent(student.id) {
                            it.copy(
                                status = ItemStatus.FAILED,
                                statusText = "Failed (0/${pending.size})"
                            )
                        }
                        onLog("[${idx + 1}/${students.size}] ${student.username} ($name): 0/${pending.size} submitted.", LogLevel.ERROR)
                    }
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
