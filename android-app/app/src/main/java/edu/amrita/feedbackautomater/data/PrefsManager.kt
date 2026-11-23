package edu.amrita.feedbackautomater.data

import android.content.Context
import edu.amrita.feedbackautomater.model.FeedbackMode
import edu.amrita.feedbackautomater.model.RatingScheme

/**
 * Stores non-sensitive user preferences locally (last email/roll, portal mode, rating).
 * Strictly NEVER stores passwords.
 */
class PrefsManager(context: Context) {
    private val prefs = context.getSharedPreferences("amrita_feedback_prefs", Context.MODE_PRIVATE)

    var lastEmailOrRoll: String
        get() = prefs.getString(KEY_EMAIL, "").orEmpty()
        set(value) = prefs.edit().putString(KEY_EMAIL, value.trim()).apply()

    var lastMode: FeedbackMode
        get() {
            val saved = prefs.getString(KEY_MODE, FeedbackMode.TLP.name)
            return FeedbackMode.entries.firstOrNull { it.name == saved } ?: FeedbackMode.TLP
        }
        set(value) = prefs.edit().putString(KEY_MODE, value.name).apply()

    var lastRating: RatingScheme
        get() {
            val saved = prefs.getString(KEY_RATING, RatingScheme.VERY_GOOD.name)
            return RatingScheme.entries.firstOrNull { it.name == saved } ?: RatingScheme.VERY_GOOD
        }
        set(value) = prefs.edit().putString(KEY_RATING, value.name).apply()

    var lastBatchRating: RatingScheme
        get() {
            val saved = prefs.getString(KEY_BATCH_RATING, RatingScheme.VERY_GOOD.name)
            return RatingScheme.entries.firstOrNull { it.name == saved } ?: RatingScheme.VERY_GOOD
        }
        set(value) = prefs.edit().putString(KEY_BATCH_RATING, value.name).apply()

    fun clearAll() {
        prefs.edit().clear().apply()
    }

    companion object {
        private const val KEY_EMAIL = "last_email_or_roll"
        private const val KEY_MODE = "last_mode"
        private const val KEY_RATING = "last_rating"
        private const val KEY_BATCH_RATING = "last_batch_rating"
    }
}
