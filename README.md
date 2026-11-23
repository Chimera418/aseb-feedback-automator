# 🎓 MyAmrita Feedback Automater

## 💖 Credits
* **[@Shaenpai24](https://github.com/Shaenpai24)**: The entire project was his original idea, and he developed the initial basic script that laid the foundation for this automater.

An automated, end-to-end tool to handle the tedious process of submitting feedback on the **MyAmrita Student Portal** (`TLP` & `Course` feedback) and the **AmritaVidya** Student Feedback System (`web-blr.amrita.edu/amritavidya`).

Available as a **native Android app** (100% on-device), plus **Streamlit** web and **Tkinter** desktop apps for PC.

---

## 📱 Android App — Amrita Feedback Automater

Run everything directly on your Android phone — no PC, no Playwright, no cloud servers, and no campus IP blocks.

### ⬇️ Download APK
Grab the latest signed APK from [**GitHub Releases →**](https://github.com/Chimera418/aseb-feedback-automator/releases/latest)

1. Download `Amrita-Feedback-Automater-v1.1.0.apk` on your Android phone (Android 8.0+).
2. Tap the APK to install (enable *"Install unknown apps"* for your browser/file manager if prompted).

### ✨ Android Features
* **100% On-Device & Private**: Runs natively on your phone's own network. Passwords, sign-in cookies, and Outlook OTPs never leave your device and are never saved to disk.
* **All Four Modes**: **TLP**, **Course**, **Course + TLP**, and **AmritaVidya** (fast direct HTTP — no browser overhead).
* **Queue & Batch Modes**:
  * **MyAmrita Queue**: Run TLP / Course / Both sequentially across multiple students with isolated sessions.
  * **AmritaVidya Batch**: Built-in roll number range generator (e.g. `bl.sc.u4aie24` `101` → `160`), bulk paste support, and randomized rating schemes.
* **Smart Roll Conversion**: Pasting an email like `bl.sc.u4aie24103@bl.students.amrita.edu` into AmritaVidya automatically converts it to `bl.sc.u4aie24103`.
* **Background Execution**: Uses an Android foreground service with live progress & finish notifications so long batches continue with the screen off or while using other apps.
* **Native Material 3 UI**: Follows your phone's light/dark theme with `#BF0C4F` Amrita accent, live activity log, and completion summary popup.

### 🛠️ Build the Android App from Source
See [`android-app/README.md`](android-app/README.md) for Android Studio & Gradle build instructions.

---

## 💻 Desktop & Web App (Python + Playwright)

The desktop/web version uses **Playwright** for browser automation to navigate the portals, handle OTP verifications through Outlook, and fill out feedback forms based on user-defined ratings. It includes both a **Streamlit** web app and a **Tkinter** desktop GUI.

### 🌟 Features

* **Four Modes**: **TLP Feedback**, **Course Feedback** (OTP-first workflow), **Both (Course + TLP)** on the MyAmrita portal, plus **AmritaVidya Feedback** on `web-blr.amrita.edu/amritavidya` (username/password only, no OTP).
* **Queue & Batch Modes**: Multi-student sequential queue for MyAmrita and batch range submission for AmritaVidya.
* **Automated OTP Handling**: Automatically logs into your Amrita Outlook email via Microsoft SSO, waits for the OTP email, extracts the 6-digit code, and verifies it on the portal.
* **Smart Polling**: Uses robust DOM-mutation polling and Javascript-alert handling to navigate through multi-step forms quickly and reliably.
* **Per-Subject Ratings**: Fetches all pending subjects and lets you set individual ratings (Excellent, Very Good, Good, etc.) before locking in submission.
* **Verified Submissions** (AmritaVidya): Reloads the feedback list after every form to confirm the course flipped off "Enter Feedback".
* **Dry Run** (AmritaVidya): Fill every form and screenshot it *without* submitting.
* **Live Logging & Headless Browser**: Runs quietly in the background with a real-time activity log.

### Mode comparison

| | TLP Feedback | Course Feedback | AmritaVidya Feedback |
|---|---|---|---|
| Site | `students.amrita.edu` | `students.amrita.edu` | `web-blr.amrita.edu/amritavidya` |
| Python Module | [`tlp.py`](tlp.py) | [`course.py`](course.py) | [`vidya.py`](vidya.py) |
| Android Engine | `WebView` + JS | `WebView` + JS | Native `OkHttp` + `Jsoup` |
| Login | Microsoft SSO | Microsoft SSO | Roll number + password |
| OTP | On finish | Before the form | None |
| Form | Multi-step, one question per page | Multi-step, one question per page | Single page, 9 questions |

### 🛠️ Prerequisites (Desktop / Web)

* **Python 3.8+**
* Google Chrome or Chromium installed.
* For **AmritaVidya** mode: network access to `web-blr.amrita.edu` (home/mobile/campus network — cloud datacenter IPs are blocked by campus firewall).

### 📦 Installation (Desktop / Web)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Chimera418/aseb-feedback-automator.git
   cd aseb-feedback-automator
   ```

2. **Create a virtual environment (recommended):**
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies & Playwright Chromium:**
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

### 🚀 Usage (Desktop / Web)

#### Option A: Streamlit Web App (Recommended)
```bash
python -m streamlit run app.py
```

#### Option B: Desktop GUI (Tkinter)
```bash
python gui.py
```

#### Option C: AmritaVidya CLI
```bash
python vidya.py --dry-run --show
```
Screenshots of every filled form land in `images/vidya_dryrun_subject_*.png`. Drop the flags to submit for real with the default rating.

> [!WARNING]
> Without `--dry-run`, `vidya.py` submits every pending feedback immediately using the default rating — there is no confirmation step. Use the Android app, GUI, or Streamlit app if you want to review or configure ratings first.

---

## 🔑 Credentials

| Mode | Username | Password |
|---|---|---|
| TLP / Course | Your Amrita email (`bl.sc.u4aieXXXXX@bl.students.amrita.edu`) or roll number | Your Microsoft password |
| AmritaVidya | Your roll number (`bl.sc.u4aieXXXXX` — emails are auto-trimmed on Android) | Your AmritaVidya password — defaults to `amma` if left blank |

On Desktop/CLI, credentials and options can also be set via environment variables: `OUTLOOK_EMAIL`, `VIDYA_USERNAME`, `VIDYA_PASSWORD`, `ANSWER_OPTION_INDEX`, `HEADLESS`, and `DRY_RUN`.

> [!NOTE]
> `amma` is only the factory default on AmritaVidya. If a student has changed their password, login fails and the log will report the portal's error message.

## 🔒 Privacy & Security

* **No credential storage or transmission**: Passwords, Microsoft SSO cookies, and Outlook OTPs are processed strictly locally on your phone or PC and are never written to disk or sent to any third-party server.
* **Secrets excluded from Git**: `android-app/local.properties`, `*.jks`, `*.keystore`, and `.env` files are git-ignored so signing keys and optional webhook URLs are never committed.

## ⚠️ Disclaimer

> [!IMPORTANT]
> **Why this exists:** Made this because manually doing feedback was a pain in the ass.
>
> **Reliability:** MyAmrita occasionally returns 504 errors during peak traffic. AmritaVidya is far more stable when run directly from your phone or local PC.
>
> **Ratings are yours:** The tool selects whatever rating scheme you choose — submitted feedback cannot be undone.

<div align="center">
  <img src="https://media.tenor.com/2XyX9r36G_MAAAAC/cat-dance.gif" alt="Dancing Cat" width="200"/>
</div>
