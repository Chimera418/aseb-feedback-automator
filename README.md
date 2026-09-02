# 🎓 MyAmrita Feedback Automater

## 💖 Credits
* **[@Shaenpai24](https://github.com/Shaenpai24)**: The entire project was his original idea, and he developed the initial basic script that laid the foundation for this automater.

An automated, end-to-end tool to handle the tedious process of submitting feedback on the MyAmrita Student Portal and the older AmritaVidya Student Feedback System.

This project uses **Playwright** for browser automation to navigate the portals, handle OTP verifications through Outlook, and fill out feedback forms based on user-defined ratings. It includes both a **Tkinter** desktop GUI and a **Streamlit** web app interface.

## 🌟 Features

* **Three Modes**: **TLP Feedback** and **Course Feedback** (OTP-first workflow) on the MyAmrita portal, plus **AmritaVidya Feedback** on the older `web-blr.amrita.edu/amritavidya` Student Feedback System (username/password only, no OTP).
* **Automated OTP Handling**: Automatically logs into your Amrita Outlook email via Microsoft SSO, waits for the OTP email, extracts the 6-digit code, and verifies it on the portal.
* **Smart Polling**: Uses robust DOM-mutation polling and Javascript-alert handling to navigate through multi-step forms quickly and reliably, bypassing slow network timeouts.
* **Per-Subject Ratings**: Fetches all pending subjects and allows you to set individual ratings (Excellent, Very Good, Good, etc.) for each course/faculty before locking in the submission.
* **Verified Submissions** (AmritaVidya): After each form, the feedback list is reloaded to confirm the course no longer shows "Enter Feedback" — anything that silently fails is reported as ❌ Failed instead of a false ✅.
* **Dry Run** (AmritaVidya): Fill every form and screenshot it *without* submitting, so you can check the answers before anything becomes permanent.
* **Live Logging**: Real-time activity log showing exactly what the bot is doing behind the scenes.
* **Headless Browser**: Runs entirely in the background without stealing mouse focus or opening visible windows.

### Mode comparison

| | TLP Feedback | Course Feedback | AmritaVidya Feedback |
|---|---|---|---|
| Site | `students.amrita.edu` | `students.amrita.edu` | `web-blr.amrita.edu/amritavidya` |
| Module | [`tlp.py`](tlp.py) | [`course.py`](course.py) | [`vidya.py`](vidya.py) |
| Login | Microsoft SSO | Microsoft SSO | Username + password |
| OTP | On finish | Before the form | None |
| Form | Multi-step, one question per page | Multi-step, one question per page | Single page, 9 questions |

## 🛠️ Prerequisites

* **Python 3.8+**
* Google Chrome or Chromium installed.
* For **AmritaVidya** mode: network access to `web-blr.amrita.edu` (campus network or VPN).

## 📦 Installation

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

3. **Install the dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install Playwright Browsers:**
   ```bash
   playwright install chromium
   ```

## 🚀 Usage

You can run the automater using either the Desktop GUI or the Streamlit Web App.

### Option A: Streamlit Web App (Recommended)
Launch the modern, responsive web interface:
```bash
python -m streamlit run app.py
```
*The app will automatically open in your default browser at `http://localhost:8501` (or similar).*

### Option B: Desktop GUI (Tkinter)
Launch the classic desktop application:
```bash
python gui.py
```

### Option C: AmritaVidya from the command line
Useful for checking the forms before committing to them. `--dry-run` fills everything but never submits, and `--show` opens a visible browser:
```bash
python vidya.py --dry-run --show
```
Screenshots of every filled form land in `images/vidya_dryrun_subject_*.png`. Drop the flags to submit for real with the default rating.

> [!WARNING]
> Without `--dry-run`, `vidya.py` submits every pending feedback immediately using the default rating — there is no confirmation step. Use the GUI or Streamlit app if you want to pick ratings per subject.

## 🔑 Credentials

| Mode | Username | Password |
|---|---|---|
| TLP / Course | Your Amrita email (`bl.sc.u4aieXXXXX@bl.students.amrita.edu`) | Your Microsoft password |
| AmritaVidya | Your roll-number login (`bl.sc.u4aieXXXXX`, no domain) | Your AmritaVidya password — defaults to `amma` if left blank |

Both can also be set via environment variables: `OUTLOOK_EMAIL`, `VIDYA_USERNAME`, `VIDYA_PASSWORD`, plus `ANSWER_OPTION_INDEX`, `HEADLESS`, and `DRY_RUN`.

> [!NOTE]
> `amma` is only the factory default on AmritaVidya. If a student has changed their password, login fails and the log will quote the portal's own message: *"Invalid User name or password."*

## 🧠 How it Works
1. **Login & Fetch**: You provide your credentials. The bot logs into the portal and scrapes the feedback list to find every subject still marked pending.
2. **Assign Ratings**: The UI presents a list of pending subjects. You can choose a custom rating for each one.
3. **Submit**: Once you click submit, the bot iterates through each subject.
   - For **Course Feedback**, it clicks "Send OTP", logs into your Outlook, reads the OTP, and enters it.
   - For **TLP** and **Course**, it then loops through every question, selects the radio button matching your chosen rating, and clicks "Save & Next" until the form is complete — finally handling the Javascript confirmation alert and clicking "Finish".
   - For **AmritaVidya**, the whole form is one page: it groups the radio buttons by question, clamps your rating to each question's option count (questions have 4 or 5 options), submits, then reloads the list to confirm the row flipped to "Submitted".
4. **Failures are isolated**: If one subject errors out, it is screenshotted into `images/`, marked ❌ Failed in the UI, and the bot moves on to the next one.

Logs are written to `logs/` (`feedback_bot.log`, `course_feedback_bot.log`, `vidya_feedback_bot.log`) and error/dry-run screenshots to `images/`.

## ⚠️ Disclaimer

> [!IMPORTANT]
> **Why this exists:** Made this because manually doing feedback was a pain in the ass.
> 
> **Reliability:** It might not work sometimes because the MyAmrita website is so unstable and constantly hits 504 errors. AmritaVidya is far more stable, but only reachable from the campus network.
>
> **Ratings are yours:** The bot picks whatever option you tell it to — it does not decide the answers for you, and submitted feedback cannot be undone.

<div align="center">
  <img src="https://media.tenor.com/2XyX9r36G_MAAAAC/cat-dance.gif" alt="Dancing Cat" width="200"/>
</div>
