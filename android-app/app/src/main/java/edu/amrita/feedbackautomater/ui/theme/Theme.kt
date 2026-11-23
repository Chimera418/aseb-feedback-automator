package edu.amrita.feedbackautomater.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

/**
 * Amrita maroon expressed through Material 3 color roles.
 * Both schemes are first-class and follow the system setting.
 */
private val LightScheme = lightColorScheme(
    primary = Color(0xFFBF0C4F),
    onPrimary = Color.White,
    primaryContainer = Color(0xFFFFD9E2),
    onPrimaryContainer = Color(0xFF3E0019),
    secondary = Color(0xFF75565C),
    onSecondary = Color.White,
    secondaryContainer = Color(0xFFF7DDE1),
    onSecondaryContainer = Color(0xFF2B1519),
    background = Color(0xFFFBF8F8),
    onBackground = Color(0xFF1E1A1B),
    surface = Color(0xFFFBF8F8),
    onSurface = Color(0xFF1E1A1B),
    surfaceVariant = Color(0xFFF2DDE0),
    onSurfaceVariant = Color(0xFF524345),
    surfaceContainerLowest = Color(0xFFFFFFFF),
    surfaceContainerLow = Color(0xFFF6F2F2),
    surfaceContainer = Color(0xFFF1EDED),
    surfaceContainerHigh = Color(0xFFEBE7E7),
    surfaceContainerHighest = Color(0xFFE5E1E2),
    outline = Color(0xFF857375),
    outlineVariant = Color(0xFFD7C1C4),
    error = Color(0xFFBA1A1A),
    onError = Color.White,
    errorContainer = Color(0xFFFFDAD6),
    onErrorContainer = Color(0xFF410002)
)

private val DarkScheme = darkColorScheme(
    primary = Color(0xFFFFB0C7),
    onPrimary = Color(0xFF66002A),
    primaryContainer = Color(0xFF8E0036),
    onPrimaryContainer = Color(0xFFFFD9E2),
    secondary = Color(0xFFE3BDC3),
    onSecondary = Color(0xFF422930),
    secondaryContainer = Color(0xFF5B3F46),
    onSecondaryContainer = Color(0xFFFFD9DF),
    background = Color(0xFF161213),
    onBackground = Color(0xFFEAE0E1),
    surface = Color(0xFF161213),
    onSurface = Color(0xFFEAE0E1),
    surfaceVariant = Color(0xFF524345),
    onSurfaceVariant = Color(0xFFD7C1C4),
    surfaceContainerLowest = Color(0xFF110D0E),
    surfaceContainerLow = Color(0xFF1E1A1B),
    surfaceContainer = Color(0xFF231E1F),
    surfaceContainerHigh = Color(0xFF2D2829),
    surfaceContainerHighest = Color(0xFF383334),
    outline = Color(0xFFA08C8F),
    outlineVariant = Color(0xFF524345),
    error = Color(0xFFFFB4AB),
    onError = Color(0xFF690005),
    errorContainer = Color(0xFF93000A),
    onErrorContainer = Color(0xFFFFDAD6)
)

@Immutable
data class SemanticColors(val success: Color, val warning: Color)

private val LightSemantic = SemanticColors(success = Color(0xFF1B6E3A), warning = Color(0xFF8A5100))
private val DarkSemantic = SemanticColors(success = Color(0xFF7DD99B), warning = Color(0xFFFFB95C))

private val LocalSemanticColors = staticCompositionLocalOf { LightSemantic }

object Semantic {
    val colors: SemanticColors
        @Composable get() = LocalSemanticColors.current
}

@Composable
fun AmritaTheme(content: @Composable () -> Unit) {
    val dark = isSystemInDarkTheme()
    CompositionLocalProvider(LocalSemanticColors provides if (dark) DarkSemantic else LightSemantic) {
        MaterialTheme(
            colorScheme = if (dark) DarkScheme else LightScheme,
            typography = Typography(),
            content = content
        )
    }
}
