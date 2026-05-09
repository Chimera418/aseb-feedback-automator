# 🎓 Amrita Feedback Automater

## 💖 Credits
* **[@Shaenpai24](https://github.com/Shaenpai24)**: The entire project was his original idea, and he developed the initial basic script that laid the foundation for this automater.

An automated, end-to-end tool to handle the tedious process of submitting TLP and Course feedbacks on the Amrita Student Portal. 

This project uses **Playwright** for browser automation to navigate the student portal, handle OTP verifications through Outlook, and fill out feedback forms based on user-defined ratings. It includes both a **Tkinter** desktop GUI and a **Streamlit** web app interface.

## 🌟 Features

* **Dual Modes**: Supports both standard **TLP Feedback** and **Course Feedback** (which requires an OTP-first workflow).
* **Automated OTP Handling**: Automatically logs into your Amrita Outlook email via Microsoft SSO, waits for the OTP email, extracts the 6-digit code, and verifies it on the portal.
* **Smart Polling**: Uses robust DOM-mutation polling and Javascript-alert handling to navigate through multi-step forms quickly and reliably, bypassing slow network timeouts.
* **Per-Subject Ratings**: Fetches all pending subjects and allows you to set individual ratings (Excellent, Very Good, Good, etc.) for each course/faculty before locking in the submission.
* **Live Logging**: Real-time activity log showing exactly what the bot is doing behind the scenes.
* **Headless Browser**: Runs entirely in the background without stealing mouse focus or opening visible windows.

## 🛠️ Prerequisites

* **Python 3.8+**
* Google Chrome or Chromium installed.

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

## 🧠 How it Works
1. **Login & Fetch**: You provide your Amrita email and password. The bot logs into the portal and scrapes your dashboard to find all subjects that currently have a "Pending" feedback status.
2. **Assign Ratings**: The UI presents a list of pending subjects. You can choose a custom rating for each one.
3. **Submit**: Once you click submit, the bot iterates through each subject.
   - For **Course Feedback**, it clicks "Send OTP", logs into your Outlook, reads the OTP, and enters it.
   - It then loops through every question, selects the radio button corresponding to your chosen rating, and clicks "Save & Next" until the form is complete.
   - Finally, it handles the Javascript confirmation alert and clicks "Finish".
## ⚠️ Disclaimer
This tool is built for educational purposes to demonstrate browser automation, DOM traversal, and asynchronous Python programming. Use it responsibly and ensure you comply with your university's IT policies.

<div align="center">
  <img src="https://media.tenor.com/2XyX9r36G_MAAAAC/cat-dance.gif" alt="Dancing Cat" width="200"/>
</div>
