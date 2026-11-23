package edu.amrita.feedbackautomater.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import edu.amrita.feedbackautomater.data.PrefsManager
import edu.amrita.feedbackautomater.engine.MyAmritaWebViewEngine
import edu.amrita.feedbackautomater.engine.VidyaHttpEngine
import edu.amrita.feedbackautomater.model.BatchStudentItem
import edu.amrita.feedbackautomater.model.FeedbackMode
import edu.amrita.feedbackautomater.model.ItemStatus
import edu.amrita.feedbackautomater.model.LogEntry
import edu.amrita.feedbackautomater.model.LogLevel
import edu.amrita.feedbackautomater.model.PendingSubject
import edu.amrita.feedbackautomater.model.QueueStudentItem
import edu.amrita.feedbackautomater.model.RatingScheme
import edu.amrita.feedbackautomater.model.normalizeAmritaEmail
import edu.amrita.feedbackautomater.model.normalizeVidyaRoll
import edu.amrita.feedbackautomater.network.EmailLoggerClient
import edu.amrita.feedbackautomater.service.AutomationService
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import edu.amrita.feedbackautomater.util.AutomationNotificationHelper
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID

enum class ActiveRunType { NONE, SINGLE, QUEUE, BATCH }

data class RunSummary(
    val title: String,
    val subtitle: String,
    val doneCount: Int,
    val skippedCount: Int,
    val failedCount: Int
)

data class MainUiState(
    val mode: FeedbackMode = FeedbackMode.TLP,
    val multiTabIndex: Int = 0, // 0 = MyAmrita Queue, 1 = AmritaVidya Batch (persisted across tab switches!)
    val activeRunType: ActiveRunType = ActiveRunType.NONE,
    val studentName: String = "",
    // Single mode fields
    val emailOrUsername: String = "",
    val password: String = "",
    val selectedRating: RatingScheme = RatingScheme.VERY_GOOD,
    val subjects: List<PendingSubject> = emptyList(),
    // MyAmrita Queue mode
    val queueItems: List<QueueStudentItem> = emptyList(),
    val queueDelaySec: Double = 2.0,
    // AmritaVidya Batch mode
    val batchItems: List<BatchStudentItem> = emptyList(),
    val batchDefaultPassword: String = "amma",
    val batchRating: RatingScheme = RatingScheme.VERY_GOOD,
    val batchDelaySec: Double = 1.5,
    // Shared logs & completion summary dialog
    val logs: List<LogEntry> = emptyList(),
    val completionSummary: RunSummary? = null
) {
    val isRunning: Boolean get() = activeRunType != ActiveRunType.NONE
}

class MainViewModel(application: Application) : AndroidViewModel(application) {

    private val prefs = PrefsManager(application.applicationContext)
    private val notifications = AutomationNotificationHelper(application.applicationContext)

    // Run state and scope outlive the Activity, so a run keeps going when the app is swiped away
    // (as long as AutomationService keeps the process alive) and the UI reattaches to it.
    private val _uiState = sharedState ?: MutableStateFlow(
        MainUiState(
            mode = prefs.lastMode,
            emailOrUsername = prefs.lastEmailOrRoll,
            selectedRating = prefs.lastRating,
            batchRating = prefs.lastBatchRating
        )
    ).also { sharedState = it }
    val uiState: StateFlow<MainUiState> = _uiState.asStateFlow()

    private var activeJob: Job?
        get() = sharedJob
        set(value) { sharedJob = value }

    private companion object {
        var sharedState: MutableStateFlow<MainUiState>? = null
        var sharedJob: Job? = null
        val runScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    }
    private val timeFmt = SimpleDateFormat("HH:mm:ss", Locale.getDefault())

    private val vidyaEngine = VidyaHttpEngine(::appendLog)
    private val myAmritaEngine = MyAmritaWebViewEngine(application.applicationContext, ::appendLog)

    fun setMode(mode: FeedbackMode) {
        if (_uiState.value.isRunning) return
        prefs.lastMode = mode
        _uiState.update {
            it.copy(
                mode = mode,
                subjects = emptyList(),
                // AmritaVidya signs in with the roll number only
                emailOrUsername = if (mode == FeedbackMode.VIDYA) normalizeVidyaRoll(it.emailOrUsername) else it.emailOrUsername
            )
        }
    }

    /** Always allowed — even while running — so users can freely inspect Queue or Batch progress. */
    fun setMultiTabIndex(index: Int) {
        _uiState.update { it.copy(multiTabIndex = index.coerceIn(0, 1)) }
    }

    fun updateSingleCredentials(email: String? = null, password: String? = null, rating: RatingScheme? = null) {
        // Pasting an Amrita email into the AmritaVidya field keeps just the roll number
        val cleanedEmail = if (email != null && _uiState.value.mode == FeedbackMode.VIDYA) {
            normalizeVidyaRoll(email)
        } else email
        if (cleanedEmail != null) prefs.lastEmailOrRoll = cleanedEmail
        if (rating != null) prefs.lastRating = rating
        _uiState.update {
            it.copy(
                emailOrUsername = cleanedEmail ?: it.emailOrUsername,
                password = password ?: it.password,
                selectedRating = rating ?: it.selectedRating
            )
        }
    }

    fun updateBatchSettings(defaultPass: String? = null, rating: RatingScheme? = null, delaySec: Double? = null) {
        if (rating != null) prefs.lastBatchRating = rating
        _uiState.update {
            it.copy(
                batchDefaultPassword = defaultPass ?: it.batchDefaultPassword,
                batchRating = rating ?: it.batchRating,
                batchDelaySec = delaySec ?: it.batchDelaySec
            )
        }
    }

    fun addBulkQueueStudents(rawText: String, mode: FeedbackMode, rating: RatingScheme) {
        val newItems = rawText.lines().mapNotNull { line ->
            val clean = line.trim()
            if (clean.isEmpty() || clean.startsWith("#")) return@mapNotNull null
            val parts = clean.split(",", limit = 2)
            if (parts.size < 2) return@mapNotNull null
            val email = normalizeAmritaEmail(parts[0])
            val pass = parts[1].trim()
            if (email.isBlank() || pass.isBlank()) return@mapNotNull null
            QueueStudentItem(
                id = UUID.randomUUID().toString(),
                email = email,
                password = pass,
                mode = if (mode == FeedbackMode.VIDYA) FeedbackMode.BOTH else mode,
                rating = rating
            )
        }
        if (newItems.isNotEmpty()) {
            _uiState.update { it.copy(queueItems = it.queueItems + newItems) }
        }
    }

    fun clearQueue() {
        if (_uiState.value.isRunning) return
        _uiState.update { it.copy(queueItems = emptyList()) }
    }

    fun removeQueueItem(id: String) {
        if (_uiState.value.isRunning) return
        _uiState.update { it.copy(queueItems = it.queueItems.filterNot { item -> item.id == id }) }
    }

    fun addBatchRange(prefix: String, startStr: String, endStr: String) {
        val start = startStr.trim().toIntOrNull() ?: return
        val end = endStr.trim().toIntOrNull() ?: return
        if (start > end) return
        val pad = maxOf(startStr.trim().length, endStr.trim().length)
        val defaultPass = _uiState.value.batchDefaultPassword.ifBlank { "amma" }
        val existingUsernames = _uiState.value.batchItems.map { it.username }.toSet()

        val generated = (start..end).mapNotNull { num ->
            val username = prefix.trim() + num.toString().padStart(pad, '0')
            if (username in existingUsernames) null
            else BatchStudentItem(
                id = UUID.randomUUID().toString(),
                username = username,
                password = defaultPass
            )
        }
        _uiState.update { it.copy(batchItems = it.batchItems + generated) }
    }

    fun addBulkBatchStudents(rawText: String) {
        val defaultPass = _uiState.value.batchDefaultPassword.ifBlank { "amma" }
        val existing = _uiState.value.batchItems.map { it.username }.toMutableSet()
        val parsed = rawText.lines().mapNotNull { line ->
            val clean = line.trim()
            if (clean.isEmpty() || clean.startsWith("#")) return@mapNotNull null
            val parts = clean.split(",", limit = 2)
            val user = normalizeVidyaRoll(parts[0])
            val pass = parts.getOrNull(1)?.trim()?.ifBlank { defaultPass } ?: defaultPass
            if (user.isBlank() || !existing.add(user)) null
            else BatchStudentItem(id = UUID.randomUUID().toString(), username = user, password = pass)
        }
        _uiState.update { it.copy(batchItems = it.batchItems + parsed) }
    }

    fun clearBatch() {
        if (_uiState.value.isRunning) return
        _uiState.update { it.copy(batchItems = emptyList()) }
    }

    fun removeBatchItem(id: String) {
        if (_uiState.value.isRunning) return
        _uiState.update { it.copy(batchItems = it.batchItems.filterNot { item -> item.id == id }) }
    }

    fun clearLogs() {
        if (_uiState.value.isRunning) return
        _uiState.update { it.copy(logs = emptyList()) }
    }

    fun dismissCompletionSummary() {
        _uiState.update { it.copy(completionSummary = null) }
    }

    fun clearSavedPreferences() {
        prefs.clearAll()
        if (!_uiState.value.isRunning) {
            _uiState.update {
                it.copy(
                    emailOrUsername = "",
                    password = "",
                    mode = FeedbackMode.TLP,
                    selectedRating = RatingScheme.VERY_GOOD,
                    batchRating = RatingScheme.VERY_GOOD
                )
            }
        }
        appendLog("Cleared saved local preferences.", LogLevel.INFO)
    }

    fun startSingleRun() {
        val state = _uiState.value
        if (state.isRunning) return
        if (state.emailOrUsername.isBlank()) {
            appendLog("Please enter your email or roll number.", LogLevel.WARN)
            return
        }
        if (state.password.isBlank() && state.mode != FeedbackMode.VIDYA) {
            appendLog("Please enter your Microsoft password.", LogLevel.WARN)
            return
        }

        val effectivePassword = state.password.ifBlank { "amma" }
        _uiState.update {
            it.copy(
                activeRunType = ActiveRunType.SINGLE,
                subjects = emptyList(),
                logs = emptyList(),
                completionSummary = null
            )
        }
        notifications.showProgress("Amrita Feedback Automater", "Running ${state.mode.label}...")
        AutomationService.start(getApplication())

        activeJob = runScope.launch {
            val loggedEmail = normalizeAmritaEmail(state.emailOrUsername)
            launch { EmailLoggerClient.logSingleUsage(loggedEmail, state.mode.label) }

            try {
                val (done, skipped, failed) = if (state.mode == FeedbackMode.VIDYA) {
                    vidyaEngine.runSingle(
                        username = normalizeVidyaRoll(state.emailOrUsername),
                        password = effectivePassword,
                        ratingScheme = state.selectedRating,
                        onStudentName = { name -> _uiState.update { it.copy(studentName = name) } },
                        onSubjectsFetched = { list -> _uiState.update { it.copy(subjects = list) } },
                        onSubjectStatus = { info, status ->
                            _uiState.update { s ->
                                s.copy(subjects = s.subjects.map { if (it.info == info) it.copy(status = status) else it })
                            }
                        }
                    )
                } else {
                    myAmritaEngine.runSingle(
                        emailOrRoll = state.emailOrUsername,
                        password = effectivePassword,
                        mode = state.mode,
                        rating = state.selectedRating,
                        onSubjectsFetched = { list -> _uiState.update { it.copy(subjects = list) } },
                        onSubjectStatus = { info, status ->
                            _uiState.update { s ->
                                s.copy(subjects = s.subjects.map { if (it.info == info) it.copy(status = status) else it })
                            }
                        }
                    )
                }

                val summaryText = when {
                    done == 0 && skipped > 0 && failed == 0 -> "All feedbacks were already submitted."
                    failed == 0 -> "Successfully submitted $done feedback(s)."
                    else -> "Submitted $done, Failed $failed."
                }
                notifications.showComplete("${state.mode.label} Complete", summaryText)
                _uiState.update {
                    it.copy(
                        completionSummary = RunSummary(
                            title = "${state.mode.label} Finished",
                            subtitle = summaryText,
                            doneCount = done,
                            skippedCount = skipped,
                            failedCount = failed
                        )
                    )
                }
            } catch (_: CancellationException) {
                notifications.cancelProgress()
            } catch (e: Exception) {
                appendLog("Error: ${e.message}", LogLevel.ERROR)
                notifications.showComplete("${state.mode.label} Failed", e.message ?: "Unexpected error")
                _uiState.update {
                    it.copy(
                        completionSummary = RunSummary(
                            title = "Run Encountered an Error",
                            subtitle = e.message ?: "Check Activity logs for details.",
                            doneCount = 0,
                            skippedCount = 0,
                            failedCount = 1
                        )
                    )
                }
            } finally {
                notifications.cancelProgress()
                AutomationService.stop(getApplication())
                _uiState.update { it.copy(activeRunType = ActiveRunType.NONE) }
            }
        }
    }

    fun startQueueRun() {
        val state = _uiState.value
        if (state.isRunning || state.queueItems.isEmpty()) return
        _uiState.update {
            it.copy(
                activeRunType = ActiveRunType.QUEUE,
                multiTabIndex = 0,
                logs = emptyList(),
                completionSummary = null
            )
        }
        notifications.showProgress("MyAmrita Queue", "Starting ${state.queueItems.size} student(s)...", 0, state.queueItems.size)
        AutomationService.start(getApplication())

        activeJob = runScope.launch {
            val allEmails = state.queueItems.map { it.email }
            launch { EmailLoggerClient.logBatchUsage(allEmails, "MyAmrita Queue") }

            try {
                val (done, skipped, failed) = myAmritaEngine.runQueue(
                    items = state.queueItems,
                    delaySeconds = state.queueDelaySec,
                    onProgress = { curr, total, label ->
                        notifications.showProgress("MyAmrita Queue ($curr/$total)", label, curr, total)
                    }
                ) { id, transform ->
                    _uiState.update { s ->
                        s.copy(queueItems = s.queueItems.map { if (it.id == id) transform(it) else it })
                    }
                }
                val msg = "Done: $done • Failed: $failed"
                notifications.showComplete("MyAmrita Queue Complete", msg)
                _uiState.update {
                    it.copy(
                        completionSummary = RunSummary(
                            title = "Queue Complete",
                            subtitle = "Processed ${state.queueItems.size} student(s) in MyAmrita Queue.",
                            doneCount = done,
                            skippedCount = skipped,
                            failedCount = failed
                        )
                    )
                }
            } catch (_: CancellationException) {
                notifications.cancelProgress()
            } finally {
                notifications.cancelProgress()
                AutomationService.stop(getApplication())
                _uiState.update { it.copy(activeRunType = ActiveRunType.NONE) }
            }
        }
    }

    fun startBatchRun() {
        val state = _uiState.value
        if (state.isRunning || state.batchItems.isEmpty()) return
        _uiState.update {
            it.copy(
                activeRunType = ActiveRunType.BATCH,
                multiTabIndex = 1,
                logs = emptyList(),
                completionSummary = null
            )
        }
        notifications.showProgress("AmritaVidya Batch", "Starting ${state.batchItems.size} student(s)...", 0, state.batchItems.size)
        AutomationService.start(getApplication())

        activeJob = runScope.launch {
            val allEmails = state.batchItems.map { normalizeAmritaEmail(it.username) }
            launch { EmailLoggerClient.logBatchUsage(allEmails, "AmritaVidya Batch") }

            try {
                val (done, skipped, failed) = vidyaEngine.runBatch(
                    students = state.batchItems,
                    ratingScheme = state.batchRating,
                    delaySeconds = state.batchDelaySec,
                    onProgress = { curr, total, label ->
                        notifications.showProgress("AmritaVidya Batch ($curr/$total)", label, curr, total)
                    }
                ) { id, transform ->
                    _uiState.update { s ->
                        s.copy(batchItems = s.batchItems.map { if (it.id == id) transform(it) else it })
                    }
                }
                val msg = "Done: $done • Skipped: $skipped • Failed: $failed"
                notifications.showComplete("AmritaVidya Batch Complete", msg)
                _uiState.update {
                    it.copy(
                        completionSummary = RunSummary(
                            title = "Batch Complete",
                            subtitle = "Processed ${state.batchItems.size} student(s) on AmritaVidya.",
                            doneCount = done,
                            skippedCount = skipped,
                            failedCount = failed
                        )
                    )
                }
            } catch (_: CancellationException) {
                notifications.cancelProgress()
            } finally {
                notifications.cancelProgress()
                AutomationService.stop(getApplication())
                _uiState.update { it.copy(activeRunType = ActiveRunType.NONE) }
            }
        }
    }

    fun cancelActiveRun() {
        activeJob?.cancel()
        activeJob = null
        notifications.cancelProgress()
        AutomationService.stop(getApplication())
        _uiState.update { it.copy(activeRunType = ActiveRunType.NONE) }
        appendLog("Stopped by user.", LogLevel.WARN)
    }

    private fun appendLog(message: String, level: LogLevel) {
        val entry = LogEntry(
            timestamp = timeFmt.format(Date()),
            message = message,
            level = level
        )
        _uiState.update { it.copy(logs = (it.logs + entry).takeLast(250)) }
    }
}
