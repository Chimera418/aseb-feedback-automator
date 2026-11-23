package edu.amrita.feedbackautomater.model

import kotlin.random.Random

enum class FeedbackMode(val label: String, val key: String) {
    TLP("TLP Feedback", "tlp"),
    COURSE("Course Feedback", "course"),
    BOTH("Both (Course + TLP)", "both"),
    VIDYA("AmritaVidya", "vidya")
}

enum class ExecutionSubMode(val label: String) {
    SINGLE("Single Student"),
    MULTI("Queue / Batch")
}

enum class RatingScheme(val label: String, val fixedIndex: Int?) {
    EXCELLENT("Excellent (0)", 0),
    VERY_GOOD("Very Good (1)", 1),
    GOOD("Good (2)", 2),
    SATISFACTORY("Satisfactory (3)", 3),
    POOR("Poor (4)", 4),
    RANDOM_MOSTLY_EXCELLENT("Random: Mostly Excellent (0 & 1)", null),
    RANDOM_MOSTLY_VERY_GOOD("Random: Mostly Very Good (1 & 2)", null),
    RANDOM_NATURAL_MIX("Random: Natural Mix (0, 1, 2)", null);

    fun resolveIndex(optionCount: Int): Int {
        val raw = when (this) {
            RANDOM_MOSTLY_EXCELLENT -> if (Random.nextInt(100) < 70) 0 else 1
            RANDOM_MOSTLY_VERY_GOOD -> if (Random.nextInt(100) < 75) 1 else 2
            RANDOM_NATURAL_MIX -> {
                val r = Random.nextInt(100)
                when {
                    r < 45 -> 0
                    r < 90 -> 1
                    else -> 2
                }
            }
            else -> fixedIndex ?: 1
        }
        return raw.coerceIn(0, (optionCount - 1).coerceAtLeast(0))
    }

    companion object {
        val singleOptions = listOf(EXCELLENT, VERY_GOOD, GOOD, SATISFACTORY, POOR)
        val batchOptions = entries.toList()
    }
}

enum class ItemStatus {
    PENDING, PROCESSING, DONE, SKIPPED, FAILED
}

data class PendingSubject(
    val info: String,
    val code: String,
    val url: String?,
    val status: ItemStatus = ItemStatus.PENDING,
    val rating: RatingScheme = RatingScheme.VERY_GOOD
)

data class QueueStudentItem(
    val id: String,
    val email: String,
    val password: String,
    val mode: FeedbackMode,
    val rating: RatingScheme,
    val status: ItemStatus = ItemStatus.PENDING,
    val statusText: String = "Pending"
)

data class BatchStudentItem(
    val id: String,
    val username: String,
    val password: String,
    val studentName: String = "",
    val pendingCount: Int? = null,
    val status: ItemStatus = ItemStatus.PENDING,
    val statusText: String = "Pending"
)

enum class LogLevel { INFO, SUCCESS, WARN, ERROR }

data class LogEntry(
    val timestamp: String,
    val message: String,
    val level: LogLevel = LogLevel.INFO
)

/** AmritaVidya logs in with the roll number only: "bl.sc.u4aie24103@bl.students.amrita.edu" -> "bl.sc.u4aie24103". */
fun normalizeVidyaRoll(input: String): String = input.trim().substringBefore('@').trim()

fun normalizeAmritaEmail(input: String): String {
    val clean = input.trim()
    if (clean.isEmpty()) return ""
    return if ("@" in clean) clean else "$clean@bl.students.amrita.edu"
}
