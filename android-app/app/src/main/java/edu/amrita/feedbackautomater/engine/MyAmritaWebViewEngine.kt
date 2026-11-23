package edu.amrita.feedbackautomater.engine

import android.content.Context
import edu.amrita.feedbackautomater.model.FeedbackMode
import edu.amrita.feedbackautomater.model.ItemStatus
import edu.amrita.feedbackautomater.model.LogLevel
import edu.amrita.feedbackautomater.model.PendingSubject
import edu.amrita.feedbackautomater.model.QueueStudentItem
import edu.amrita.feedbackautomater.model.RatingScheme
import edu.amrita.feedbackautomater.model.normalizeAmritaEmail
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import org.json.JSONArray

/**
 * Client-side MyAmrita (TLP & Course) automation engine powered by Android WebView.
 * Handles Microsoft SSO, Outlook Web OTP scraping, and multi-step feedback forms locally on-device.
 */
class MyAmritaWebViewEngine(
    private val context: Context,
    private val onLog: (String, LogLevel) -> Unit
) {
    companion object {
        private const val DASHBOARD_URL = "https://students.amrita.edu/client/index"
        private const val TLP_URL = "https://students.amrita.edu/client/class-feedback"
        private const val COURSE_URL = "https://students.amrita.edu/client/course-feedback-list"
        private const val OUTLOOK_URL = "https://outlook.office.com/mail/inbox"
    }

    private suspend fun loginToMicrosoft(wv: WebViewController, email: String, password: String) {
        onLog("Waiting for Microsoft login page...", LogLevel.INFO)
        if (!wv.waitForSelector("input[name='loginfmt']", 25_000L)) {
            onLog("Already authenticated or redirected.", LogLevel.INFO)
            return
        }

        wv.fillInput("input[name='loginfmt']", email)
        wv.clickSelector("#idSIButton9")
        delay(2000)

        if (wv.waitForSelector("div[data-bind*='EstsAccountType_WorkSchool']", 3_500L)) {
            wv.clickSelector("div[data-bind*='EstsAccountType_WorkSchool']")
            delay(1500)
        }

        for (attempt in 1..6) {
            if (wv.waitForSelector("input[name='passwd']", 2_500L)) break

            // 1. Direct "Use your password instead" / "Use my password" link (e.g. on Authenticator notification screen)
            val clickedPwd = wv.clickSelector("#idA_PWD_SwitchToPassword") ||
                wv.clickSelector("a[id*='SwitchToPassword']") ||
                wv.clickSelector("[data-bind*='SwitchToPassword']") ||
                wv.clickSelector("div[data-value='Password']") ||
                wv.clickElementByText("a, button, [role='link'], [role='button'], div, span", "use your password instead") ||
                wv.clickElementByText("a, button, [role='link'], [role='button'], div, span", "use my password") ||
                wv.clickElementByText("a, button, [role='link'], [role='button']", "sign in with a password")
            if (clickedPwd) {
                onLog("Switched to password sign-in (attempt $attempt)...", LogLevel.INFO)
                delay(2000)
                if (wv.waitForSelector("input[name='passwd']", 4_000L)) break
                continue
            }

            // 2. Fallback: "Other ways to sign in" / "Sign-in options"
            val clickedOther = wv.clickSelector("#signInAnotherWay") ||
                wv.clickElementByText("a, button, [role='link'], [role='button']", "other ways to sign in") ||
                wv.clickElementByText("a, button, [role='link'], [role='button']", "sign-in options") ||
                wv.clickElementByText("a, button, [role='link'], [role='button']", "i can't use my microsoft authenticator")
            if (clickedOther) {
                onLog("Opened other sign-in options...", LogLevel.INFO)
                delay(2000)
            }
        }

        if (!wv.waitForSelector("input[name='passwd']", 15_000L)) {
            throw RuntimeException("Password field did not appear on Microsoft login.")
        }

        wv.fillInput("input[name='passwd']", password)
        wv.clickSelector("#idSIButton9")
        delay(2500)

        if (wv.waitForSelector("#idBtn_Back", 5_000L)) {
            wv.clickSelector("#idBtn_Back")
            delay(2000)
        }
        onLog("Microsoft SSO login submitted.", LogLevel.SUCCESS)
    }

    private suspend fun ensurePortalLoggedIn(wv: WebViewController, email: String, password: String) {
        wv.loadUrl(DASHBOARD_URL)
        delay(1500)
        val clickedInitialLogin = wv.clickElementByText("span, a, button", "login")
        if (clickedInitialLogin) {
            delay(2000)
        }
        val url = wv.currentUrl()
        if ("login.microsoftonline.com" in url || wv.waitForSelector("input[name='loginfmt']", 3_000L)) {
            loginToMicrosoft(wv, email, password)
            delay(3000)
        }
    }

    private suspend fun fetchOtpFromOutlook(
        outlookWv: WebViewController,
        email: String,
        password: String
    ): String {
        onLog("Opening Outlook Web to fetch OTP...", LogLevel.INFO)
        outlookWv.loadUrl(OUTLOOK_URL)
        delay(2500)
        if ("login.microsoftonline.com" in outlookWv.currentUrl()) {
            loginToMicrosoft(outlookWv, email, password)
            delay(4000)
        }

        val otpRegex = Regex("""\b(\d{6})\b""")
        for (attempt in 1..12) {
            outlookWv.clickElementByText("span, div", "otp for student portal feedback")
            delay(1500)
            val bodyText = outlookWv.evalJs(
                """
                (function() {
                    const el = document.querySelector("div[aria-label*='Message body'], div.BodyFragment, div[role='document']");
                    return el ? el.innerText : '';
                })()
                """.trimIndent()
            )
            val match = otpRegex.find(bodyText)
            if (match != null) {
                val otp = match.groupValues[1]
                onLog("Fetched OTP successfully.", LogLevel.SUCCESS)
                return otp
            }
            onLog("Waiting for OTP email (attempt $attempt/12)...", LogLevel.INFO)
            delay(4000)
        }
        throw RuntimeException("Timed out waiting for OTP email in Outlook.")
    }

    private suspend fun collectPendingSubjects(wv: WebViewController, listUrl: String): List<PendingSubject> {
        wv.loadUrl(listUrl)
        delay(1500)
        val jsonStr = wv.evalJs(
            """
            (function() {
                const rows = Array.from(document.querySelectorAll('table#home_tab tr, table tr'));
                const out = [];
                for (const row of rows) {
                    const link = Array.from(row.querySelectorAll('a')).find(a =>
                        (a.innerText || '').toLowerCase().includes('submit feedback')
                    );
                    if (!link) continue;
                    const cells = Array.from(row.querySelectorAll('td, th')).map(c => c.innerText.trim());
                    out.push({
                        info: (cells[1] || cells[0] || 'Subject') + ' | ' + (cells[2] || ''),
                        code: cells[1] || cells[0] || '',
                        url: link.href || ''
                    });
                }
                return JSON.stringify(out);
            })()
            """.trimIndent()
        )
        val list = mutableListOf<PendingSubject>()
        if (jsonStr.isNotBlank()) {
            val arr = JSONArray(jsonStr)
            for (i in 0 until arr.length()) {
                val obj = arr.getJSONObject(i)
                list.add(
                    PendingSubject(
                        info = obj.optString("info"),
                        code = obj.optString("code"),
                        url = obj.optString("url").ifBlank { null }
                    )
                )
            }
        }
        return list
    }

    private suspend fun sendAndVerifyOtp(
        portalWv: WebViewController,
        outlookWv: WebViewController,
        email: String,
        password: String
    ) {
        val sent = portalWv.clickElementByText("button, a", "send otp")
        if (!sent) return
        onLog("Requested OTP from portal...", LogLevel.INFO)
        delay(3000)
        val otp = fetchOtpFromOutlook(outlookWv, email, password)
        portalWv.fillInput("input[placeholder*='OTP' i], input[name*='otp' i]", otp)
        delay(500)
        portalWv.clickElementByText("button", "validate") ||
            portalWv.clickElementByText("button", "verify") ||
            portalWv.clickSelector("button[name='otp_ver']")
        delay(2500)
    }

    private suspend fun fillMultiStepQuestions(wv: WebViewController, rating: RatingScheme) {
        for (step in 1..40) {
            val chosenIdx = rating.resolveIndex(5)
            val stepResult = wv.evalJs(
                """
                (function() {
                    const finishBtn = document.querySelector("button[name='finish_feedback']") ||
                        Array.from(document.querySelectorAll('button')).find(b =>
                            b.offsetParent !== null && (b.innerText || '').trim().toLowerCase() === 'finish'
                        );
                    if (finishBtn && finishBtn.offsetParent !== null) {
                        finishBtn.click();
                        return 'FINISHED';
                    }

                    const activeRadios = Array.from(document.querySelectorAll("input[type='radio']"))
                        .filter(r => r.offsetParent !== null);
                    if (activeRadios.length > 0) {
                        const target = activeRadios[Math.min($chosenIdx, activeRadios.length - 1)];
                        target.checked = true;
                        target.click();
                        target.dispatchEvent(new Event('change', { bubbles: true }));
                    }

                    const nextBtn = document.querySelector("button[name='submit_ans'], .next-btn") ||
                        Array.from(document.querySelectorAll('button')).find(b => {
                            if (b.offsetParent === null) return false;
                            const t = (b.innerText || '').trim().toLowerCase();
                            return t === 'next' || t === 'save & next' || t === 'save' || t === 'proceed';
                        });
                    if (nextBtn) {
                        nextBtn.click();
                        return 'NEXT';
                    }
                    return 'DONE';
                })()
                """.trimIndent()
            )
            delay(1000)
            if (stepResult == "FINISHED" || stepResult == "DONE") break
        }
    }

    suspend fun runSingle(
        emailOrRoll: String,
        password: String,
        mode: FeedbackMode,
        rating: RatingScheme,
        onSubjectsFetched: (List<PendingSubject>) -> Unit = {},
        onSubjectStatus: (String, ItemStatus) -> Unit = { _, _ -> }
    ): Triple<Int, Int, Int> {
        val email = normalizeAmritaEmail(emailOrRoll)
        val portalWv = WebViewController(context)
        val outlookWv = WebViewController(context)
        var doneCount = 0
        var failedCount = 0
        var totalFound = 0
        try {
            portalWv.clearAllCookies()
            ensurePortalLoggedIn(portalWv, email, password)

            val phases = when (mode) {
                FeedbackMode.BOTH -> listOf(FeedbackMode.COURSE, FeedbackMode.TLP)
                else -> listOf(mode)
            }

            for (phase in phases) {
                val listUrl = if (phase == FeedbackMode.COURSE) COURSE_URL else TLP_URL
                onLog("Checking ${phase.label} for $email...", LogLevel.INFO)
                val pending = collectPendingSubjects(portalWv, listUrl)
                totalFound += pending.size
                onSubjectsFetched(pending)
                onLog("Found ${pending.size} pending ${phase.label} item(s).", LogLevel.INFO)

                for ((idx, item) in pending.withIndex()) {
                    onSubjectStatus(item.info, ItemStatus.PROCESSING)
                    onLog("[${idx + 1}/${pending.size}] ${item.info}", LogLevel.INFO)
                    try {
                        if (item.url != null) portalWv.loadUrl(item.url)
                        delay(1500)

                        if (phase == FeedbackMode.COURSE) {
                            sendAndVerifyOtp(portalWv, outlookWv, email, password)
                            fillMultiStepQuestions(portalWv, rating)
                        } else {
                            fillMultiStepQuestions(portalWv, rating)
                            sendAndVerifyOtp(portalWv, outlookWv, email, password)
                        }
                        onSubjectStatus(item.info, ItemStatus.DONE)
                        onLog("Completed ${item.info}", LogLevel.SUCCESS)
                        doneCount++
                    } catch (e: CancellationException) {
                        throw e
                    } catch (e: Exception) {
                        onSubjectStatus(item.info, ItemStatus.FAILED)
                        onLog("Failed ${item.info}: ${e.message}", LogLevel.ERROR)
                        failedCount++
                    }
                }
            }
            onLog("MyAmrita automation complete for $email!", LogLevel.SUCCESS)
            val skipped = if (totalFound == 0) 1 else 0
            return Triple(doneCount, skipped, failedCount)
        } finally {
            portalWv.destroy()
            outlookWv.destroy()
        }
    }

    suspend fun runQueue(
        items: List<QueueStudentItem>,
        delaySeconds: Double,
        onProgress: (current: Int, total: Int, label: String) -> Unit = { _, _, _ -> },
        onUpdateItem: (id: String, transform: (QueueStudentItem) -> QueueStudentItem) -> Unit
    ): Triple<Int, Int, Int> {
        onLog("Starting MyAmrita Queue (${items.size} student(s))...", LogLevel.INFO)
        var doneCount = 0
        var failedCount = 0
        for ((idx, item) in items.withIndex()) {
            onProgress(idx + 1, items.size, "Processing ${item.email}")
            onUpdateItem(item.id) {
                it.copy(status = ItemStatus.PROCESSING, statusText = "Running ${item.mode.label}...")
            }
            try {
                runSingle(
                    emailOrRoll = item.email,
                    password = item.password,
                    mode = item.mode,
                    rating = item.rating
                )
                doneCount++
                onUpdateItem(item.id) {
                    it.copy(status = ItemStatus.DONE, statusText = "Done")
                }
            } catch (e: CancellationException) {
                onLog("Queue cancelled by user.", LogLevel.WARN)
                throw e
            } catch (e: Exception) {
                failedCount++
                val err = e.message?.take(40) ?: "Error"
                onUpdateItem(item.id) {
                    it.copy(status = ItemStatus.FAILED, statusText = "Failed")
                }
                onLog("Queue item ${item.email} failed: $err", LogLevel.ERROR)
            }
            if (delaySeconds > 0 && idx < items.lastIndex) {
                delay((delaySeconds * 1000).toLong())
            }
        }
        onLog("MyAmrita Queue finished — Done: $doneCount, Failed: $failedCount", LogLevel.SUCCESS)
        return Triple(doneCount, 0, failedCount)
    }
}
