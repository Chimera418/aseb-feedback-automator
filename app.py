import streamlit as st
import threading
import asyncio
import logging
import queue
import time
import os
import subprocess
import sys
import pandas as pd

# Ensure Playwright Chromium browser is installed (essential for Streamlit Cloud deployment)
@st.cache_resource
def install_playwright():
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True,
            text=True,
            timeout=180
        )
    except Exception as e:
        print(f"Playwright auto-install notice: {e}")

install_playwright()

import tlp
import course
import vidya
import myamrita_queue

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MyAmrita Feedback Automater",
    page_icon="🎓",
    layout="wide",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Inter font */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    /* App background */
    .stApp { background: #0f0f1a; color: #e2e8f0; }

    /* Sidebar */
    [data-testid="stSidebar"] { background: #1a1a2e; border-right: 1px solid #2d2d4e; }

    /* Branded header */
    .app-header {
        background: linear-gradient(135deg, #bf0c4f 0%, #7c1d6f 100%);
        padding: 20px 28px;
        border-radius: 14px;
        margin-bottom: 24px;
        box-shadow: 0 4px 24px rgba(191,12,79,.35);
    }
    .app-header h1 { color: #fff; margin: 0; font-size: 1.7rem; font-weight: 700; }
    .app-header p  { color: rgba(255,255,255,.75); margin: 4px 0 0; font-size: .9rem; }

    /* Cards */
    .card {
        background: #1e1e30;
        border: 1px solid #2d2d4e;
        border-radius: 12px;
        padding: 20px 24px;
        margin-bottom: 18px;
    }
    .card-title {
        font-size: .75rem;
        font-weight: 600;
        letter-spacing: .08em;
        text-transform: uppercase;
        color: #7c85a2;
        margin-bottom: 14px;
    }

    /* Subject table row */
    .subject-row {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 10px 14px;
        border-radius: 8px;
        background: #252540;
        margin-bottom: 6px;
        border: 1px solid #2d2d4e;
    }
    .subject-name { flex: 2; font-size: .85rem; font-weight: 500; color: #c9d1e3; }
    .subject-class { flex: 2; font-size: .8rem; color: #7c85a2; }

    /* Status badges */
    .badge {
        display: inline-flex; align-items: center; gap: 5px;
        padding: 3px 10px; border-radius: 20px;
        font-size: .78rem; font-weight: 600; white-space: nowrap;
    }
    .badge-pending  { background: #2d2d4e; color: #a0aec0; }
    .badge-process  { background: #1e3a5f; color: #60a5fa; }
    .badge-done     { background: #14532d; color: #4ade80; }
    .badge-failed   { background: #450a0a; color: #f87171; }

    /* Log area */
    .log-area {
        background: #0d0d1a;
        border: 1px solid #2d2d4e;
        border-radius: 10px;
        padding: 16px;
        font-family: 'Courier New', monospace;
        font-size: .78rem;
        color: #a0aec0;
        height: 280px;
        overflow-y: auto;
        line-height: 1.6;
        white-space: pre-wrap;
        word-break: break-word;
    }
    .log-line-info    { color: #a0aec0; }
    .log-line-success { color: #4ade80; }
    .log-line-error   { color: #f87171; }
    .log-line-warn    { color: #fbbf24; }

    /* Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #bf0c4f, #7c1d6f) !important;
        color: #fff !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        padding: 8px 22px !important;
        transition: opacity .2s !important;
    }
    .stButton > button:hover  { opacity: .85 !important; }
    .stButton > button:disabled { opacity: .4 !important; cursor: not-allowed !important; }

    /* Radio buttons */
    .stRadio > div { flex-direction: row; gap: 18px; }
    .stRadio label { color: #c9d1e3 !important; }

    /* Text inputs */
    .stTextInput > div > div > input,
    .stSelectbox > div > div {
        background: #252540 !important;
        border: 1px solid #3d3d60 !important;
        border-radius: 8px !important;
        color: #e2e8f0 !important;
    }

    /* Selectbox items */
    .stSelectbox > div { color: #e2e8f0 !important; }

    /* Hide streamlit branding */
    #MainMenu, footer, header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ── Rating options ─────────────────────────────────────────────────────────────
RATING_OPTIONS = ["Excellent (0)", "Very Good (1)", "Good (2)", "Satisfactory (3)", "Poor (4)"]

BATCH_RATING_OPTIONS = [
    "Very Good (1)",
    "Excellent (0)",
    "Good (2)",
    "Satisfactory (3)",
    "Poor (4)",
    "Randomized: Mostly Excellent (0 & 1)",
    "Randomized: Mostly Very Good (1 & 2)",
    "Randomized: Natural Mix (0, 1, 2)",
]

def parse_rating(rating_val) -> int:
    if isinstance(rating_val, int):
        return rating_val
    try:
        s = str(rating_val)
        if "(" in s and ")" in s:
            return int(s.split("(")[1].split(")")[0])
        return int(s.strip())
    except Exception:
        return 1

# ── Session-state bootstrap ────────────────────────────────────────────────────
def init_state():
    defaults = {
        "ui_queue":               queue.Queue(),
        "user_config_queue":      queue.Queue(),
        "subjects":               [],       # list of {info, course_name, class_name, status, rating}
        "batch_students":         [],       # list of dicts for batch table
        "batch_stats":            {"total": 0, "success": 0, "skipped": 0, "failed": 0, "processed": 0},
        "is_myamrita_queue_running": False, # True while actively running MyAmrita queue
        "myamrita_queue_list":    [],       # list of dicts for MyAmrita queue table
        "myamrita_queue_stats":   {"total": 0, "success": 0, "failed": 0, "processed": 0},
        "log_lines":              [],
        "running":                False,    # True only while actively fetching or submitting
        "is_fetching":            False,    # True while actively logging in & scraping list
        "is_submitting":          False,    # True while actively filling & submitting forms
        "is_batch_running":       False,    # True while actively running AmritaVidya batch
        "awaiting_submit":        False,    # True when subjects are fetched and waiting for user review
        "done":                   False,
        "student_name":           "",       # fetched after login
        "run_id":                 0,        # increments per run to isolate events & keys
        "current_mode":           "tlp",
        "default_rating_choice":  "Very Good (1)",
        "batch_text_input_area":  "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# ── Logging bridge ─────────────────────────────────────────────────────────────
class QueueHandler(logging.Handler):
    def __init__(self, q: queue.Queue):
        super().__init__()
        self._q = q
        self.run_id = 0
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))

    def emit(self, record):
        try:
            self._q.put((self.run_id, "log", self.format(record)))
        except Exception:
            pass

_log_q = st.session_state["ui_queue"]
_current_rid = st.session_state.get("run_id", 0)

# Remove any stale QueueHandlers (added by previous reruns), then attach one fresh one
for _lgr in (tlp.logger, course.logger, vidya.logger, myamrita_queue.logger):
    _lgr.handlers = [h for h in _lgr.handlers if h.__class__.__name__ != "QueueHandler"]
    _h = QueueHandler(_log_q)
    _h.run_id = _current_rid
    _lgr.addHandler(_h)
    _lgr.setLevel(logging.INFO)

# ── Background threads ─────────────────────────────────────────────────────────
def run_asyncio_loop(run_id, email, password, default_idx, mode, ui_queue, user_config_queue, target_host=None, proxy=None, auto_submit=False):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        if mode == "both":
            loop.run_until_complete(
                myamrita_queue.run_single_chained(
                    email=email,
                    password=password,
                    mode="both",
                    answer_idx=default_idx,
                    headless=True,
                    progress_callback=lambda etype, data: ui_queue.put((run_id, etype, data)),
                    user_config_queue=user_config_queue,
                    auto_submit=auto_submit,
                )
            )
        else:
            module_to_run = {"tlp": tlp, "course": course, "vidya": vidya}[mode]
            effective_q = None if auto_submit else user_config_queue
            run_kwargs = {
                "email": email,
                "password": password,
                "answer_idx": default_idx,
                "headless": True,
                "progress_callback": lambda etype, data: ui_queue.put((run_id, etype, data)),
                "user_config_queue": effective_q,
            }
            if mode == "vidya":
                if target_host:
                    run_kwargs["target_host"] = target_host
                if proxy:
                    run_kwargs["proxy"] = proxy
            loop.run_until_complete(module_to_run.run(**run_kwargs))
    except Exception as e:
        tlp.logger.error(f"Fatal error in automation loop: {e}")
    finally:
        try:
            loop.close()
        except Exception:
            pass
        ui_queue.put((run_id, "thread_done", None))

def run_asyncio_myamrita_queue_loop(run_id, queue_items, delay_sec, ui_queue, cancel_queue):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(
            myamrita_queue.run_queue(
                queue_items=queue_items,
                delay_between_students=delay_sec,
                headless=True,
                progress_callback=lambda etype, data: ui_queue.put((run_id, etype, data)),
                cancel_queue=cancel_queue,
            )
        )
    except Exception as e:
        tlp.logger.error(f"Fatal error in MyAmrita queue loop: {e}")
    finally:
        try:
            loop.close()
        except Exception:
            pass
        ui_queue.put((run_id, "myamrita_queue_thread_done", None))

def run_asyncio_batch_loop(run_id, students, rating_choice, delay_sec, ui_queue, cancel_queue, target_host=None, proxy=None):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(
            vidya.run_batch(
                students=students,
                answer_idx=rating_choice,
                delay_between_students=delay_sec,
                headless=True,
                progress_callback=lambda etype, data: ui_queue.put((run_id, etype, data)),
                cancel_queue=cancel_queue,
                target_host=target_host,
                proxy=proxy,
            )
        )
    except Exception as e:
        vidya.logger.error(f"Fatal error in batch loop: {e}")
    finally:
        try:
            loop.close()
        except Exception:
            pass
        ui_queue.put((run_id, "batch_thread_done", None))

# ── Queue drain (called every rerun) ──────────────────────────────────────────
def drain_queue():
    q = st.session_state["ui_queue"]
    current_run_id = st.session_state.get("run_id", 0)
    changed = False
    while True:
        try:
            item = q.get_nowait()
        except queue.Empty:
            break

        if len(item) == 3:
            event_run_id, event_type, data = item
            if event_run_id != current_run_id:
                # Stale message from an older run — discard
                continue
        elif len(item) == 2:
            event_type, data = item
        else:
            continue

        changed = True

        if event_type == "log":
            st.session_state["log_lines"].append(data)

        elif event_type == "fetch_complete":
            pass

        elif event_type == "waiting_for_user":
            subjects = []
            default_r = st.session_state.get("default_rating_choice", "Very Good (1)")
            for item_dict in data:
                info = item_dict["info"]
                parts = info.split(" | ")
                course_name = parts[0][:55] + "…" if len(parts[0]) > 55 else parts[0]
                class_name  = parts[1] if len(parts) > 1 else ""
                subjects.append({
                    "info":        info,
                    "course_name": course_name,
                    "class_name":  class_name,
                    "status":      "pending",
                    "rating":      default_r,
                })
            st.session_state["subjects"]        = subjects
            st.session_state["is_fetching"]     = False
            st.session_state["is_submitting"]   = False
            st.session_state["awaiting_submit"] = True
            st.session_state["running"]         = False

        elif event_type == "subject_processing":
            for s in st.session_state["subjects"]:
                if s["info"] == data:
                    s["status"] = "processing"

        elif event_type == "subject_done":
            for s in st.session_state["subjects"]:
                if s["info"] == data:
                    s["status"] = "done"

        elif event_type == "subject_failed":
            for s in st.session_state["subjects"]:
                if s["info"] == data:
                    s["status"] = "failed"

        elif event_type == "student_name":
            if data:
                st.session_state["student_name"] = data

        elif event_type == "thread_done":
            was_submitting = st.session_state.get("is_submitting", False)
            was_fetching   = st.session_state.get("is_fetching", False)
            st.session_state["is_fetching"]   = False
            st.session_state["is_submitting"] = False
            st.session_state["running"]       = False
            if was_submitting:
                st.session_state["done"] = True
                st.session_state["awaiting_submit"] = False
            elif was_fetching and not st.session_state.get("awaiting_submit", False):
                st.session_state["done"] = True

        # ── Batch Mode Events ─────────────────────────────────────────────────
        elif event_type == "batch_start":
            st.session_state["is_batch_running"] = True
            st.session_state["batch_stats"] = data.get("stats", {})
            st.session_state["done"] = False

        elif event_type == "batch_student_start":
            u = data["username"]
            for s in st.session_state["batch_students"]:
                if s["Roll Number"] == u:
                    s["Status"] = "🔐 Logging in..."

        elif event_type == "batch_student_name":
            u = data["username"]
            for s in st.session_state["batch_students"]:
                if s["Roll Number"] == u:
                    s["Student Name"] = data["name"]

        elif event_type == "batch_student_pending":
            u = data["username"]
            for s in st.session_state["batch_students"]:
                if s["Roll Number"] == u:
                    s["Feedbacks"] = f"{data['pending_count']} pending"
                    s["Status"] = f"📝 Submitting (0/{data['pending_count']})..."
            if "stats" in data:
                st.session_state["batch_stats"] = data["stats"]

        elif event_type == "batch_student_submitting":
            u = data["username"]
            for s in st.session_state["batch_students"]:
                if s["Roll Number"] == u:
                    s["Status"] = f"📝 Submitting ({data['current']}/{data['total']})..."

        elif event_type == "batch_student_done":
            u = data["username"]
            for s in st.session_state["batch_students"]:
                if s["Roll Number"] == u:
                    s["Status"] = f"✅ Done ({data['submitted_count']} submitted)"
            if "stats" in data:
                st.session_state["batch_stats"] = data["stats"]

        elif event_type == "batch_student_skipped":
            u = data["username"]
            for s in st.session_state["batch_students"]:
                if s["Roll Number"] == u:
                    s["Feedbacks"] = "0"
                    s["Status"] = "⚪ Already Done"
            if "stats" in data:
                st.session_state["batch_stats"] = data["stats"]

        elif event_type == "batch_student_failed":
            u = data["username"]
            for s in st.session_state["batch_students"]:
                if s["Roll Number"] == u:
                    s["Status"] = f"❌ Failed ({data['error']})"
            if "stats" in data:
                st.session_state["batch_stats"] = data["stats"]

        elif event_type == "batch_complete":
            st.session_state["is_batch_running"] = False
            st.session_state["done"] = True
            st.session_state["batch_stats"] = data

        elif event_type == "batch_thread_done":
            st.session_state["is_batch_running"] = False
            st.session_state["running"] = False

        # ── MyAmrita Queue Mode Events ────────────────────────────────────────
        elif event_type == "queue_start":
            st.session_state["is_myamrita_queue_running"] = True
            st.session_state["running"] = True
            st.session_state["done"] = False
            if "stats" in data:
                st.session_state["myamrita_queue_stats"] = data["stats"]

        elif event_type == "queue_student_start":
            em = data["email"]
            for s in st.session_state.get("myamrita_queue_list", []):
                if s.get("Email / Roll") == em or s.get("email") == em:
                    s["Status"] = f"🔐 Starting ({data.get('mode_label', '')})..."

        elif event_type == "queue_student_step":
            em = data["email"]
            for s in st.session_state.get("myamrita_queue_list", []):
                if s.get("Email / Roll") == em or s.get("email") == em:
                    s["Status"] = data["status"]

        elif event_type == "queue_student_done":
            em = data["email"]
            for s in st.session_state.get("myamrita_queue_list", []):
                if s.get("Email / Roll") == em or s.get("email") == em:
                    s["Status"] = "✅ Done"
            if "stats" in data:
                st.session_state["myamrita_queue_stats"] = data["stats"]

        elif event_type == "queue_student_failed":
            em = data["email"]
            err = data.get("error", "Error")
            for s in st.session_state.get("myamrita_queue_list", []):
                if s.get("Email / Roll") == em or s.get("email") == em:
                    s["Status"] = f"❌ Failed ({err[:30]})"
            if "stats" in data:
                st.session_state["myamrita_queue_stats"] = data["stats"]

        elif event_type == "queue_complete":
            st.session_state["is_myamrita_queue_running"] = False
            st.session_state["running"] = False
            st.session_state["done"] = True
            st.session_state["myamrita_queue_stats"] = data

        elif event_type == "myamrita_queue_thread_done":
            st.session_state["is_myamrita_queue_running"] = False
            st.session_state["running"] = False

    return changed

# ── Helper: format log lines with colour ──────────────────────────────────────
def render_log_html(lines):
    html_lines = []
    for line in lines[-200:]:
        l = line.lower()
        if "❌" in line or "error" in l or "fatal" in l or "failed" in l:
            css = "log-line-error"
        elif "✅" in line or "done" in l or "success" in l or "🎉" in line:
            css = "log-line-success"
        elif "⚠" in line or "warn" in l or "retrying" in l:
            css = "log-line-warn"
        else:
            css = "log-line-info"
        safe = line.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        html_lines.append(f'<span class="{css}">{safe}</span>')
    content = "<br>".join(html_lines)
    return f'<div class="log-area">{content}</div>'

STATUS_BADGE = {
    "pending":    '<span class="badge badge-pending">⏳ Pending</span>',
    "processing": '<span class="badge badge-process">🔄 Processing…</span>',
    "done":       '<span class="badge badge-done">✅ Done</span>',
    "failed":     '<span class="badge badge-failed">❌ Failed</span>',
}

# ══════════════════════════════════════════════════════════════════════════════
#  UI
# ══════════════════════════════════════════════════════════════════════════════
drain_queue()

student_name = st.session_state.get("student_name", "")
greeting_html = f'<p>👋 Welcome, <strong>{student_name}</strong></p>' if student_name else '<p>Automate TLP, Course, and AmritaVidya feedback submissions</p>'
st.markdown(f"""
<div class="app-header">
    <h1>🎓 MyAmrita Feedback Automater</h1>
    {greeting_html}
</div>
""", unsafe_allow_html=True)

# ── Step 1 ─────────────────────────────────────────────────────────────────────
st.markdown('<div class="card"><div class="card-title">Step 1 — Setup &amp; Configuration</div>', unsafe_allow_html=True)

MODES = {
    "TLP Feedback": "tlp",
    "Course Feedback": "course",
    "🔄 Both (Course + TLP)": "both",
    "AmritaVidya Feedback": "vidya",
}

mode = st.radio("Feedback Mode", list(MODES.keys()), horizontal=True, key="mode_radio")
mode_key = MODES[mode]
is_vidya = mode_key == "vidya"

# Detect mode switch and reset pending state if mode changed
if "current_mode" in st.session_state and st.session_state["current_mode"] != mode_key:
    if (st.session_state.get("awaiting_submit") or st.session_state.get("is_batch_running") or st.session_state.get("is_myamrita_queue_running")) and st.session_state.get("user_config_queue"):
        try:
            st.session_state["user_config_queue"].put_nowait("CANCEL")
        except Exception:
            pass
    st.session_state["run_id"]            = st.session_state.get("run_id", 0) + 1
    st.session_state["subjects"]          = []
    st.session_state["batch_students"]    = []
    st.session_state["awaiting_submit"]   = False
    st.session_state["done"]              = False
    st.session_state["is_fetching"]       = False
    st.session_state["is_submitting"]     = False
    st.session_state["is_batch_running"]  = False
    st.session_state["is_myamrita_queue_running"] = False
    st.session_state["running"]           = False
st.session_state["current_mode"] = mode_key

if is_vidya:
    vidya_submode = st.radio(
        "AmritaVidya Execution Mode",
        ["👤 Single Student", "⚡ Batch Submit Mode (Multiple Students)"],
        horizontal=True,
        key="vidya_submode_choice"
    )
    is_batch_mode = "Batch" in vidya_submode
    is_queue_mode = False

    with st.expander("🌐 Portal IP & Proxy Settings (Optional)", expanded=False):
        net_col1, net_col2 = st.columns([1, 1])
        with net_col1:
            target_ip_choice = st.selectbox(
                "Portal Host / Direct IP Address",
                [
                    "210.212.205.26 (Public Direct IP — Recommended)",
                    "web-blr.amrita.edu (Standard Domain)",
                    "192.168.2.26 (Campus Wi-Fi Intranet IP)",
                    "Custom IP / URL...",
                ],
                index=0,
                key="vidya_target_ip_choice",
                help="Using direct IP (210.212.205.26) connects directly without DNS lookups."
            )
            if "Custom" in target_ip_choice:
                custom_host = st.text_input("Enter Custom IP or Hostname", value="210.212.205.26", key="vidya_custom_host")
                effective_target_host = custom_host.strip()
            else:
                effective_target_host = target_ip_choice.split(" ")[0].strip()
        with net_col2:
            default_proxy_val = ""
            try:
                if "HTTP_PROXY" in st.secrets:
                    default_proxy_val = st.secrets["HTTP_PROXY"]
            except Exception:
                pass
            outbound_proxy_input = st.text_input(
                "Outbound Proxy IP (Optional)",
                value=default_proxy_val,
                key="vidya_outbound_proxy",
                placeholder="http://user:pass@ip:port or http://ip:port",
                help="Route browser traffic through a custom proxy IP (e.g. Indian proxy to bypass Streamlit Cloud restrictions)."
            )
            effective_proxy = outbound_proxy_input.strip() if outbound_proxy_input.strip() else None
else:
    is_batch_mode = False
    effective_target_host = None
    effective_proxy = None

    myamrita_submode = st.radio(
        "MyAmrita Execution Mode",
        ["👤 Single Student", "⚡ Queue Mode (Multiple Students / Tasks)"],
        horizontal=True,
        key="myamrita_submode_choice"
    )
    is_queue_mode = "Queue" in myamrita_submode

if not is_batch_mode and not is_queue_mode:
    # ── Single Student Mode ───────────────────────────────────────────────────
    col1, col2, col3 = st.columns([3, 3, 2])
    with col1:
        email = st.text_input(
            "AmritaVidya Username" if is_vidya else "MyAmrita Email",
            value=vidya.VIDYA_USERNAME if is_vidya else tlp.OUTLOOK_EMAIL,
            key=f"email_input_{mode_key}",
            placeholder="bl.sc.u4aieXXXXX" if is_vidya else "you@bl.students.amrita.edu",
        )
    with col2:
        password = st.text_input(
            "Password",
            type="password",
            key=f"password_input_{mode_key}",
            placeholder="Leave blank to use the default" if is_vidya else "Your Microsoft password",
        )
    with col3:
        default_rating = st.selectbox("Default Rating", RATING_OPTIONS, index=1, key="default_rating")

    is_busy = st.session_state.get("is_fetching", False) or st.session_state.get("is_submitting", False)
    has_subjects = bool(st.session_state.get("subjects"))
    fetch_btn_label = "🔄 Re-fetch Subjects" if (has_subjects or st.session_state.get("done")) else "🔍 Fetch Subjects"

    btn_col1, btn_col2, btn_col3 = st.columns([2.5, 2, 1])
    with btn_col1:
        run_fully_clicked = st.button(
            "🚀 Run Fully (Auto-Submit)",
            disabled=is_busy,
            key="run_fully_btn",
            help="Runs completely without stopping to ask. Automatically submits all feedbacks with chosen rating."
        )
    with btn_col2:
        fetch_clicked = st.button(
            fetch_btn_label,
            disabled=is_busy,
            key="fetch_btn",
            help="Fetches subjects first so you can review/tweak individual faculty ratings before submitting."
        )
    with btn_col3:
        can_cancel = is_busy or st.session_state.get("awaiting_submit", False)
        cancel_clicked = st.button("⏹ Cancel", disabled=not can_cancel, key="cancel_btn")

    if st.session_state.get("is_fetching"):
        st.info("⏳ Connecting to portal and fetching pending feedbacks... Please wait.")
    elif st.session_state.get("is_submitting"):
        st.info("🚀 Submitting feedbacks... Live updates below.")

    st.markdown("</div>", unsafe_allow_html=True)

    # Cancel handler
    if cancel_clicked:
        if st.session_state.get("user_config_queue"):
            try:
                st.session_state["user_config_queue"].put_nowait("CANCEL")
            except Exception:
                pass
        st.session_state["run_id"]          = st.session_state.get("run_id", 0) + 1
        st.session_state["is_fetching"]     = False
        st.session_state["is_submitting"]   = False
        st.session_state["awaiting_submit"] = False
        st.session_state["running"]         = False
        st.session_state["log_lines"].append("🛑 Operation cancelled by user.")
        st.rerun()

    # Run Fully Handler (No intermediate prompts, submits with upfront rating)
    if run_fully_clicked:
        if not email or (not password and not is_vidya):
            st.error("Please enter both Email and Password.")
        else:
            if st.session_state.get("user_config_queue"):
                try:
                    st.session_state["user_config_queue"].put_nowait("CANCEL")
                except Exception:
                    pass

            new_run_id = st.session_state.get("run_id", 0) + 1
            st.session_state["run_id"]                = new_run_id
            st.session_state["subjects"]              = []
            st.session_state["log_lines"]             = []
            st.session_state["done"]                  = False
            st.session_state["awaiting_submit"]       = False
            st.session_state["is_fetching"]           = False
            st.session_state["is_submitting"]         = True
            st.session_state["running"]               = True
            st.session_state["student_name"]          = ""
            st.session_state["user_config_queue"]     = queue.Queue()
            st.session_state["default_rating_choice"] = default_rating

            for _lgr in (tlp.logger, course.logger, vidya.logger, myamrita_queue.logger):
                for _h in _lgr.handlers:
                    if hasattr(_h, "run_id"):
                        _h.run_id = new_run_id

            default_idx = parse_rating(default_rating)
            _ui_q  = st.session_state["ui_queue"]
            _ucq   = st.session_state["user_config_queue"]

            t = threading.Thread(
                target=run_asyncio_loop,
                args=(new_run_id, email, password, default_idx, mode_key, _ui_q, _ucq, effective_target_host, effective_proxy, True),
                daemon=True,
            )
            t.start()
            st.rerun()

    # Fetch handler (Review first)
    if fetch_clicked:
        if not email or (not password and not is_vidya):
            st.error("Please enter both Email and Password.")
        else:
            if st.session_state.get("user_config_queue"):
                try:
                    st.session_state["user_config_queue"].put_nowait("CANCEL")
                except Exception:
                    pass

            new_run_id = st.session_state.get("run_id", 0) + 1
            st.session_state["run_id"]                = new_run_id
            st.session_state["subjects"]              = []
            st.session_state["log_lines"]             = []
            st.session_state["done"]                  = False
            st.session_state["awaiting_submit"]       = False
            st.session_state["is_fetching"]           = True
            st.session_state["is_submitting"]         = False
            st.session_state["running"]               = True
            st.session_state["student_name"]          = ""
            st.session_state["user_config_queue"]     = queue.Queue()
            st.session_state["default_rating_choice"] = default_rating

            for _lgr in (tlp.logger, course.logger, vidya.logger, myamrita_queue.logger):
                for _h in _lgr.handlers:
                    if hasattr(_h, "run_id"):
                        _h.run_id = new_run_id

            default_idx = parse_rating(default_rating)
            _ui_q  = st.session_state["ui_queue"]
            _ucq   = st.session_state["user_config_queue"]

            t = threading.Thread(
                target=run_asyncio_loop,
                args=(new_run_id, email, password, default_idx, mode_key, _ui_q, _ucq, effective_target_host, effective_proxy, False),
                daemon=True,
            )
            t.start()
            st.rerun()

    # ── Single Step 2 ─────────────────────────────────────────────────────────
    st.markdown('<div class="card"><div class="card-title">Step 2 — Assign Ratings &amp; Submit</div>', unsafe_allow_html=True)
    subjects = st.session_state["subjects"]

    if not subjects:
        if st.session_state.get("is_fetching"):
            st.markdown('<p style="color:#60a5fa;font-size:.85rem;text-align:center;padding:24px 0;">🔄 Fetching subjects from portal...</p>', unsafe_allow_html=True)
        elif st.session_state.get("done"):
            st.markdown('<p style="color:#4ade80;font-size:.85rem;text-align:center;padding:24px 0;">🎉 No pending feedbacks remaining!</p>', unsafe_allow_html=True)
        else:
            st.markdown('<p style="color:#7c85a2;font-size:.85rem;text-align:center;padding:24px 0;">No subjects fetched yet. Click "Fetch Subjects" above.</p>', unsafe_allow_html=True)
    else:
        # Quick Set All Bar
        qc1, qc2 = st.columns([3, 1])
        with qc1:
            bulk_subj_rating = st.selectbox(
                "Change All Subjects Rating To:",
                RATING_OPTIONS,
                index=RATING_OPTIONS.index(st.session_state.get("default_rating_choice", "Very Good (1)")) if st.session_state.get("default_rating_choice") in RATING_OPTIONS else 1,
                key="bulk_subj_rating_selector",
                disabled=not st.session_state.get("awaiting_submit", False)
            )
        with qc2:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            apply_all_subj_clicked = st.button(
                "⚡ Apply to All",
                disabled=not st.session_state.get("awaiting_submit", False),
                key="apply_all_subj_btn",
                use_container_width=True
            )
        if apply_all_subj_clicked:
            for s in subjects:
                if s["status"] == "pending":
                    s["rating"] = bulk_subj_rating
            st.rerun()

        hcols = st.columns([3, 3, 2, 1.5])
        for h, lbl in zip(hcols, ["Course", "Class", "Rating", "Status"]):
            h.markdown(f'<span style="font-size:.72rem;font-weight:600;letter-spacing:.07em;text-transform:uppercase;color:#7c85a2;">{lbl}</span>', unsafe_allow_html=True)

        for i, s in enumerate(subjects):
            c1, c2, c3, c4 = st.columns([3, 3, 2, 1.5])
            with c1:
                st.markdown(f'<span style="font-size:.84rem;color:#c9d1e3;font-weight:500;">{s["course_name"]}</span>', unsafe_allow_html=True)
            with c2:
                st.markdown(f'<span style="font-size:.8rem;color:#7c85a2;">{s["class_name"]}</span>', unsafe_allow_html=True)
            with c3:
                disabled = s["status"] in ("processing", "done", "failed") or not st.session_state.get("awaiting_submit", False)
                new_rating = st.selectbox(
                    label="rating",
                    options=RATING_OPTIONS,
                    index=RATING_OPTIONS.index(s["rating"]) if s["rating"] in RATING_OPTIONS else 1,
                    key=f"rating_{st.session_state.get('run_id', 0)}_{i}",
                    label_visibility="collapsed",
                    disabled=disabled,
                )
                subjects[i]["rating"] = new_rating
            with c4:
                st.markdown(STATUS_BADGE.get(s["status"], ""), unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        submit_clicked = st.button(
            "🚀 Submit All Feedbacks",
            disabled=not st.session_state.get("awaiting_submit", False) or st.session_state.get("is_submitting", False),
            key="submit_btn",
        )

        if submit_clicked and st.session_state.get("awaiting_submit", False):
            config = {}
            for s in subjects:
                config[s["info"]] = parse_rating(s["rating"])
            st.session_state["user_config_queue"].put(config)
            st.session_state["awaiting_submit"] = False
            st.session_state["is_submitting"]   = True
            st.session_state["running"]         = True
            tlp.logger.info("GUI: Ratings locked in. Resuming bot execution...")
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

elif is_queue_mode:
    # ── MyAmrita Queue Mode (Course / TLP / Both) ─────────────────────────────
    with st.expander("➕ Add Single Student to Queue", expanded=True):
        q_col1, q_col2, q_col3, q_col4 = st.columns([2.5, 2, 2, 2])
        with q_col1:
            q_email = st.text_input("Amrita Email or Roll Number", placeholder="bl.sc.u4aie24001", key="q_single_email")
        with q_col2:
            q_pwd = st.text_input("Password", type="password", key="q_single_pwd")
        with q_col3:
            q_mode = st.selectbox(
                "Feedback Portal",
                ["🔄 Both (Course + TLP)", "📘 Course Feedback", "📗 TLP Feedback"],
                key="q_single_mode"
            )
        with q_col4:
            q_rating = st.selectbox("Rating Scheme", RATING_OPTIONS, index=1, key="q_single_rating")

        q_add_btn = st.button("➕ Add Student to Queue", key="q_single_add_btn")
        if q_add_btn:
            clean_em = myamrita_queue.normalize_email(q_email)
            if not clean_em or not q_pwd:
                st.error("Please enter both Email/Roll and Password.")
            else:
                mode_code = "both" if "Both" in q_mode else ("course" if "Course" in q_mode else "tlp")
                q_list = st.session_state.get("myamrita_queue_list", [])
                q_list.append({
                    "#": len(q_list) + 1,
                    "Email / Roll": clean_em,
                    "password": q_pwd,
                    "mode": mode_code,
                    "Portal Mode": q_mode,
                    "Rating": q_rating,
                    "Status": "⏳ Queued"
                })
                st.session_state["myamrita_queue_list"] = q_list
                st.success(f"Added {clean_em} to queue!")
                st.rerun()

    with st.expander("📋 Bulk Add Students (Text Paste)", expanded=False):
        st.markdown(
            "Paste multiple students, one per line. Formats supported:<br>"
            "• <code>roll_or_email,password</code><br>"
            "• <code>roll_or_email,password,mode</code> (mode: <code>both</code>, <code>course</code>, <code>tlp</code>)<br>"
            "• <code>roll_or_email,password,mode,rating_idx</code> (rating_idx: <code>0</code>, <code>1</code>, <code>2</code>, <code>3</code>, <code>4</code>)",
            unsafe_allow_html=True
        )
        bulk_text = st.text_area("Student List", height=120, key="q_bulk_text_area", placeholder="bl.sc.u4aie24001,amma,both\nbl.sc.u4aie24002,amma,both\nbl.sc.u4aie24003,amma,course")

        b_c1, b_c2, b_c3 = st.columns([2, 2, 2])
        with b_c1:
            bulk_def_pwd = st.text_input("Default Password (if omitted)", value="amma", key="q_bulk_def_pwd")
        with b_c2:
            bulk_def_mode = st.selectbox("Default Mode", ["🔄 Both (Course + TLP)", "📘 Course Feedback", "📗 TLP Feedback"], key="q_bulk_def_mode")
        with b_c3:
            bulk_def_rating = st.selectbox("Default Rating", RATING_OPTIONS, index=1, key="q_bulk_def_rating")

        b_btn1, b_btn2 = st.columns([1, 1])
        with b_btn1:
            bulk_add_btn = st.button("➕ Add All to Queue", key="q_bulk_add_btn", use_container_width=True)
        with b_btn2:
            bulk_clear_btn = st.button("🗑 Clear Queue", key="q_bulk_clear_btn", use_container_width=True)

        if bulk_add_btn and bulk_text.strip():
            def_mode_code = "both" if "Both" in bulk_def_mode else ("course" if "Course" in bulk_def_mode else "tlp")
            lines = [l.strip() for l in bulk_text.strip().splitlines() if l.strip() and not l.strip().startswith("#")]
            q_list = st.session_state.get("myamrita_queue_list", [])
            added_cnt = 0
            for line in lines:
                parts = [p.strip() for p in line.replace(":", ",").split(",") if p.strip()]
                if not parts:
                    continue
                em = myamrita_queue.normalize_email(parts[0])
                pwd = parts[1] if len(parts) > 1 else bulk_def_pwd
                m_code = parts[2].lower() if len(parts) > 2 else def_mode_code
                if m_code not in ("both", "course", "tlp"):
                    m_code = def_mode_code
                m_label = "🔄 Both (Course + TLP)" if m_code == "both" else ("📘 Course Feedback" if m_code == "course" else "📗 TLP Feedback")
                r_label = bulk_def_rating
                if len(parts) > 3 and parts[3].isdigit():
                    idx_val = int(parts[3])
                    for opt in RATING_OPTIONS:
                        if f"({idx_val})" in opt:
                            r_label = opt
                            break
                q_list.append({
                    "#": len(q_list) + 1,
                    "Email / Roll": em,
                    "password": pwd,
                    "mode": m_code,
                    "Portal Mode": m_label,
                    "Rating": r_label,
                    "Status": "⏳ Queued"
                })
                added_cnt += 1
            st.session_state["myamrita_queue_list"] = q_list
            st.session_state["q_bulk_text_area"] = ""
            st.success(f"Added {added_cnt} students to queue!")
            st.rerun()

        if bulk_clear_btn:
            st.session_state["myamrita_queue_list"] = []
            st.rerun()

    # Queue controls: delay and start/stop
    q_ctrl1, q_ctrl2, q_ctrl3 = st.columns([2, 2, 2])
    with q_ctrl1:
        q_delay = st.number_input("Delay Between Students (sec)", min_value=0.5, max_value=15.0, value=2.0, step=0.5, key="q_delay_input")
    with q_ctrl2:
        q_start_btn = st.button(
            "🚀 Start Queue Execution",
            disabled=st.session_state.get("is_myamrita_queue_running", False) or len(st.session_state.get("myamrita_queue_list", [])) == 0,
            key="q_start_btn",
            use_container_width=True
        )
    with q_ctrl3:
        q_cancel_btn = st.button(
            "⏹ Stop / Cancel Queue",
            disabled=not st.session_state.get("is_myamrita_queue_running", False),
            key="q_cancel_btn",
            use_container_width=True
        )

    st.markdown("</div>", unsafe_allow_html=True)

    if q_cancel_btn:
        if st.session_state.get("user_config_queue"):
            try:
                st.session_state["user_config_queue"].put_nowait("CANCEL")
            except Exception:
                pass
        st.session_state["log_lines"].append("🛑 MyAmrita queue cancellation requested by user...")
        st.rerun()

    if q_start_btn:
        q_items_raw = st.session_state.get("myamrita_queue_list", [])
        if not q_items_raw:
            st.error("Queue is empty. Please add students first.")
        else:
            new_run_id = st.session_state.get("run_id", 0) + 1
            st.session_state["run_id"] = new_run_id
            st.session_state["log_lines"] = []
            st.session_state["done"] = False
            st.session_state["is_myamrita_queue_running"] = True
            st.session_state["running"] = True
            st.session_state["user_config_queue"] = queue.Queue()

            # Reset statuses in queue list
            for item in q_items_raw:
                item["Status"] = "⏳ Queued"

            st.session_state["myamrita_queue_stats"] = {
                "total": len(q_items_raw),
                "success": 0,
                "failed": 0,
                "processed": 0
            }

            for _lgr in (tlp.logger, course.logger, vidya.logger, myamrita_queue.logger):
                for _h in _lgr.handlers:
                    if hasattr(_h, "run_id"):
                        _h.run_id = new_run_id

            _ui_q = st.session_state["ui_queue"]
            _cq   = st.session_state["user_config_queue"]

            prepared_items = []
            for item in q_items_raw:
                prepared_items.append({
                    "email": item["Email / Roll"],
                    "password": item["password"],
                    "mode": item["mode"],
                    "answer_idx": parse_rating(item["Rating"]),
                })

            t = threading.Thread(
                target=run_asyncio_myamrita_queue_loop,
                args=(new_run_id, prepared_items, float(q_delay), _ui_q, _cq),
                daemon=True,
            )
            t.start()
            st.rerun()

    # Step 2: Queue Table & Status
    st.markdown('<div class="card"><div class="card-title">Step 2 — MyAmrita Queue Status</div>', unsafe_allow_html=True)
    q_stats = st.session_state.get("myamrita_queue_stats", {})
    q_tot = q_stats.get("total", len(st.session_state.get("myamrita_queue_list", [])))
    q_succ = q_stats.get("success", 0)
    q_fail = q_stats.get("failed", 0)
    q_proc = q_stats.get("processed", 0)

    qm1, qm2, qm3 = st.columns(3)
    qm1.metric("👥 Total Students", q_tot)
    qm2.metric("✅ Successfully Completed", q_succ)
    qm3.metric("❌ Failed / Error", q_fail)

    if q_tot > 0:
        st.progress(min(1.0, q_proc / q_tot))

    if st.session_state.get("myamrita_queue_list"):
        # Bulk rating change controls
        with st.expander("⚡ Change Ratings for Queued Students", expanded=True):
            r_c1, r_c2 = st.columns([3, 1])
            with r_c1:
                bulk_q_rating = st.selectbox(
                    "Set Rating Scheme for All Queued Students:",
                    RATING_OPTIONS,
                    index=1,
                    key="bulk_q_rating_choice",
                    disabled=st.session_state.get("is_myamrita_queue_running", False)
                )
            with r_c2:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                apply_q_all_clicked = st.button(
                    "⚡ Apply to All",
                    disabled=st.session_state.get("is_myamrita_queue_running", False),
                    key="apply_q_all_btn",
                    use_container_width=True
                )
            if apply_q_all_clicked:
                for it in st.session_state["myamrita_queue_list"]:
                    if it.get("Status") == "⏳ Queued":
                        it["Rating"] = bulk_q_rating
                st.success(f"All queued students updated to '{bulk_q_rating}'!")
                st.rerun()

        display_rows = [
            {"#": item["#"], "Student Email / Roll": item["Email / Roll"], "Mode": item["Portal Mode"], "Rating": item["Rating"], "Status": item["Status"]}
            for item in st.session_state["myamrita_queue_list"]
        ]
        is_q_running = st.session_state.get("is_myamrita_queue_running", False)
        edited_df = st.data_editor(
            pd.DataFrame(display_rows),
            column_config={
                "Rating": st.column_config.SelectboxColumn(
                    "Rating",
                    options=RATING_OPTIONS,
                    required=True,
                ),
                "Mode": st.column_config.SelectboxColumn(
                    "Mode",
                    options=["🔄 Both (Course + TLP)", "📘 Course Feedback", "📗 TLP Feedback"],
                    required=True,
                )
            },
            disabled=["#", "Student Email / Roll", "Status"] if not is_q_running else ["#", "Student Email / Roll", "Mode", "Rating", "Status"],
            use_container_width=True,
            hide_index=True,
            key="queue_editor_table"
        )
        if not is_q_running:
            for edited_row in edited_df.to_dict(orient="records"):
                for it in st.session_state["myamrita_queue_list"]:
                    if it["#"] == edited_row["#"] and it.get("Status") == "⏳ Queued":
                        it["Rating"] = edited_row["Rating"]
                        it["Portal Mode"] = edited_row["Mode"]
                        it["mode"] = "both" if "Both" in edited_row["Mode"] else ("course" if "Course" in edited_row["Mode"] else "tlp")
    else:
        st.markdown('<p style="color:#7c85a2;font-size:.85rem;text-align:center;padding:24px 0;">Queue is empty. Add students above and click Start Queue Execution.</p>', unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

else:
    # ── Batch Submit Mode (AmritaVidya Only) ──────────────────────────────────
    with st.expander("⚡ Quick Roll Number Range Generator", expanded=True):
        rg_col1, rg_col2, rg_col3 = st.columns([2, 1, 1])
        with rg_col1:
            gen_prefix = st.text_input("Roll Prefix", value="bl.sc.u4aie24", key="gen_prefix")
        with rg_col2:
            gen_start = st.text_input("Start Roll", value="001", key="gen_start")
        with rg_col3:
            gen_end = st.text_input("End Roll", value="010", key="gen_end")

        btn_c1, btn_c2 = st.columns([1, 1])
        with btn_c1:
            gen_btn = st.button("➕ Add to List", key="gen_add_btn", use_container_width=True)
        with btn_c2:
            clear_btn = st.button("🗑 Clear List", key="gen_clear_btn", use_container_width=True)

        if gen_btn:
            s_clean = gen_start.strip()
            e_clean = gen_end.strip()
            if s_clean.isdigit() and e_clean.isdigit() and int(s_clean) <= int(e_clean):
                s_num, e_num = int(s_clean), int(e_clean)
                pad = max(len(s_clean), len(e_clean))
                prefix = gen_prefix.strip()
                new_rolls = [f"{prefix}{str(i).zfill(pad)}" for i in range(s_num, e_num + 1)]
                curr_txt = st.session_state.get("batch_text_input_area", "")
                if curr_txt.strip():
                    st.session_state["batch_text_input_area"] = curr_txt.strip() + "\n" + "\n".join(new_rolls)
                else:
                    st.session_state["batch_text_input_area"] = "\n".join(new_rolls)
                st.rerun()
            else:
                st.error("Please enter valid start and end roll numbers (e.g. 001 to 010).")

        if clear_btn:
            st.session_state["batch_text_input_area"] = ""
            st.rerun()

    # Count unique students currently in queue
    curr_input = st.session_state.get("batch_text_input_area", "")
    lines = [l.strip() for l in curr_input.splitlines() if l.strip() and not l.strip().startswith("#")]
    unique_count = len(dict.fromkeys(lines))

    batch_input_val = st.text_area(
        f"Student Roll Numbers ({unique_count} queued) — one per line:",
        height=160,
        key="batch_text_input_area",
        help="Format: username or username,password (one per line)"
    )

    b_cfg1, b_cfg2, b_cfg3 = st.columns([2, 2, 1])
    with b_cfg1:
        batch_password = st.text_input("Default Password", value="amma", key="batch_pwd_input")
    with b_cfg2:
        batch_rating = st.selectbox("Rating Scheme", BATCH_RATING_OPTIONS, index=0, key="batch_rating_choice")
    with b_cfg3:
        batch_delay = st.number_input("Delay (sec)", min_value=0.0, max_value=10.0, value=1.5, step=0.5, key="batch_delay_input")

    b_btn_col1, b_btn_col2 = st.columns([3, 1])
    with b_btn_col1:
        start_batch_clicked = st.button(
            "🚀 Start Batch Submission",
            disabled=st.session_state.get("is_batch_running", False),
            key="batch_start_btn"
        )
    with b_btn_col2:
        cancel_batch_clicked = st.button(
            "⏹ Cancel Batch",
            disabled=not st.session_state.get("is_batch_running", False),
            key="batch_cancel_btn"
        )

    st.markdown("</div>", unsafe_allow_html=True)

    # Cancel Batch
    if cancel_batch_clicked:
        if st.session_state.get("user_config_queue"):
            try:
                st.session_state["user_config_queue"].put_nowait("CANCEL")
            except Exception:
                pass
        st.session_state["log_lines"].append("🛑 Batch cancellation requested by user...")
        st.rerun()

    # Start Batch
    if start_batch_clicked:
        raw_lines = st.session_state.get("batch_text_input_area", "").strip().splitlines()
        students_list = []
        seen = set()
        for line in raw_lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.replace(":", ",").split(",") if p.strip()]
            user = parts[0]
            if user in seen:
                continue
            seen.add(user)
            pwd = parts[1] if len(parts) > 1 else (batch_password or "amma")
            students_list.append({"username": user, "password": pwd})

        if not students_list:
            st.error("Please enter or generate at least one student roll number.")
        else:
            new_run_id = st.session_state.get("run_id", 0) + 1
            st.session_state["run_id"]           = new_run_id
            st.session_state["log_lines"]        = []
            st.session_state["done"]             = False
            st.session_state["is_batch_running"] = True
            st.session_state["running"]          = True
            st.session_state["user_config_queue"] = queue.Queue()

            # Initialize batch table
            st.session_state["batch_students"] = [
                {"#": idx, "Roll Number": s["username"], "Student Name": "—", "Feedbacks": "—", "Status": "⏳ Queued"}
                for idx, s in enumerate(students_list, start=1)
            ]
            st.session_state["batch_stats"] = {
                "total": len(students_list),
                "success": 0,
                "skipped": 0,
                "failed": 0,
                "processed": 0
            }

            for _lgr in (tlp.logger, course.logger, vidya.logger):
                for _h in _lgr.handlers:
                    if hasattr(_h, "run_id"):
                        _h.run_id = new_run_id

            _ui_q = st.session_state["ui_queue"]
            _cq   = st.session_state["user_config_queue"]

            t = threading.Thread(
                target=run_asyncio_batch_loop,
                args=(new_run_id, students_list, batch_rating, float(batch_delay), _ui_q, _cq, effective_target_host, effective_proxy),
                daemon=True,
            )
            t.start()
            st.rerun()

    # ── Batch Step 2: Progress & Status Table ─────────────────────────────────
    st.markdown('<div class="card"><div class="card-title">Step 2 — Batch Progress &amp; Status</div>', unsafe_allow_html=True)
    batch_stats = st.session_state.get("batch_stats", {})
    tot = batch_stats.get("total", 0)
    done_cnt = batch_stats.get("success", 0)
    skip_cnt = batch_stats.get("skipped", 0)
    fail_cnt = batch_stats.get("failed", 0)
    proc_cnt = batch_stats.get("processed", 0)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Students", tot)
    m2.metric("✅ Successfully Submitted", done_cnt)
    m3.metric("⚪ Already Completed", skip_cnt)
    m4.metric("❌ Failed / Error", fail_cnt)

    if tot > 0:
        progress_val = min(1.0, proc_cnt / tot)
        st.progress(progress_val)

    if st.session_state.get("batch_students"):
        df = pd.DataFrame(st.session_state["batch_students"])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.markdown('<p style="color:#7c85a2;font-size:.85rem;text-align:center;padding:24px 0;">No batch running. Add students above and start batch submission.</p>', unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ── Activity Log ───────────────────────────────────────────────────────────────
st.markdown('<div class="card"><div class="card-title">📋 Activity Log</div>', unsafe_allow_html=True)
log_html = render_log_html(st.session_state["log_lines"])
st.markdown(log_html, unsafe_allow_html=True)

if st.session_state["done"]:
    if is_batch_mode:
        st.success(f"🎉 Batch submission complete! Processed {proc_cnt}/{tot} students.")
    elif is_queue_mode:
        q_st = st.session_state.get("myamrita_queue_stats", {})
        st.success(f"🎉 MyAmrita queue complete! Processed {q_st.get('processed', 0)}/{q_st.get('total', 0)} students.")
    else:
        if not st.session_state["subjects"]:
            st.info("🎉 No pending feedbacks found! You're all set.")
        else:
            st.success("🎉 Automation complete! All feedbacks have been processed.")

st.markdown("</div>", unsafe_allow_html=True)

# ── Auto-rerun while bot is actively working in background ────────────────────
if (
    st.session_state.get("is_fetching", False)
    or st.session_state.get("is_submitting", False)
    or st.session_state.get("is_batch_running", False)
    or st.session_state.get("is_myamrita_queue_running", False)
):
    time.sleep(0.8)
    st.rerun()
