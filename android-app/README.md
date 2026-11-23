# Amrita Feedback Automater (Android — Native Kotlin)

Native Android (Kotlin + Jetpack Compose + Material 3) client that automates **TLP**, **Course**, **Course + TLP**, and **AmritaVidya** feedbacks — including **MyAmrita Queue** and **AmritaVidya Batch** modes — 100% on-device.

## Architecture
- **MyAmrita (TLP & Course):** Headless Android `WebView` (`WebViewController.kt` + `MyAmritaWebViewEngine.kt`) handles Microsoft SSO (including automatic `"Use your password instead"` switching), Outlook Web OTP extraction, and multi-step forms locally.
- **AmritaVidya:** Pure `OkHttp` + `Jsoup` (`VidyaHttpEngine.kt`) with isolated in-memory cookie jars per student for fast single and batch runs.
- **Background Execution:** `AutomationService` foreground service + `PARTIAL_WAKE_LOCK` + live progress & completion notifications (`AutomationNotificationHelper.kt`).
- **Privacy:** Passwords, cookies, and OTPs never leave the phone and are never stored on disk.

## Building from Source

1. Open the `android-app/` folder in **Android Studio** (Ladybug or newer) and wait for Gradle Sync.
2. Build a debug APK via **Build → Generate App Bundles or APKs → Generate APKs** (or run `gradle assembleDebug` from `android-app/`).

### Optional `local.properties` Configuration (Git-Ignored)

All values below are optional and stay strictly local in `android-app/local.properties`:

```properties
# Android SDK location (auto-filled by Android Studio)
sdk.dir=/path/to/Android/Sdk

# Optional: Discord webhook for email-only usage telemetry (never sends passwords)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN

# Optional: Release keystore for signed release builds (gradle assembleRelease)
RELEASE_STORE_FILE=release-keystore.jks
RELEASE_STORE_PASSWORD=your_store_password
RELEASE_KEY_ALIAS=your_key_alias
RELEASE_KEY_PASSWORD=your_key_password
```

Without a release keystore configured, debug builds (`assembleDebug`) work out of the box.
