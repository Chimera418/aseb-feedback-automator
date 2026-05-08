import streamlit as st
import threading
import asyncio
import logging
import queue
import time
import os

# Ensure Playwright browsers are installed (essential for Streamlit Cloud deployment)
os.system("playwright install chromium")

import tlp
import course

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Amrita Feedback Automater",
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

def parse_rating(rating_str: str) -> int:
    try:
        return int(rating_str.split("(")[1].split(")")[0])
    except Exception:
        return 1

# ── Session-state bootstrap ────────────────────────────────────────────────────
def init_state():
    defaults = {
        "ui_queue":          queue.Queue(),
        "user_config_queue": queue.Queue(),
        "subjects":          [],       # list of {info, course_name, class_name, status, rating}
        "log_lines":         [],
        "running":           False,
        "awaiting_submit":   False,
        "done":              False,
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
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))

    def emit(self, record):
        self._q.put(("log", self.format(record)))

_log_q = st.session_state["ui_queue"]

# Remove any stale QueueHandlers (added by previous reruns), then attach one fresh one
for _lgr in (tlp.logger, course.logger):
    # Use class name check because 'isinstance' fails after Streamlit reloads the module
    _lgr.handlers = [h for h in _lgr.handlers if h.__class__.__name__ != "QueueHandler"]
    _h = QueueHandler(_log_q)
    _lgr.addHandler(_h)
    _lgr.setLevel(logging.INFO)

# ── Background thread ──────────────────────────────────────────────────────────
# NOTE: st.session_state is NOT accessible from background threads.
# Queues must be passed directly as arguments.
def run_asyncio_loop(email, password, default_idx, mode, ui_queue, user_config_queue):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        module_to_run = tlp if mode == "tlp" else course
        loop.run_until_complete(
            module_to_run.run(
                email=email,
                password=password,
                answer_idx=default_idx,
                headless=True,
                progress_callback=lambda etype, data: ui_queue.put((etype, data)),
                user_config_queue=user_config_queue,
            )
        )
    except Exception as e:
        tlp.logger.error(f"Fatal error in automation loop: {e}")
    finally:
        loop.close()
        ui_queue.put(("thread_done", None))

# ── Queue drain (called every rerun) ──────────────────────────────────────────
def drain_queue():
    q = st.session_state["ui_queue"]
    changed = False
    while True:
        try:
            event_type, data = q.get_nowait()
        except queue.Empty:
            break
        changed = True

        if event_type == "log":
            st.session_state["log_lines"].append(data)

        elif event_type == "fetch_complete":
            pass  # subjects added on waiting_for_user

        elif event_type == "waiting_for_user":
            subjects = []
            for item in data:
                info = item["info"]
                parts = info.split(" | ")
                course_name = parts[0][:55] + "…" if len(parts[0]) > 55 else parts[0]
                class_name  = parts[1] if len(parts) > 1 else ""
                subjects.append({
                    "info":        info,
                    "course_name": course_name,
                    "class_name":  class_name,
                    "status":      "pending",
                    "rating":      "Very Good (1)",
                })
            st.session_state["subjects"]       = subjects
            st.session_state["awaiting_submit"] = True

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

        elif event_type == "thread_done":
            st.session_state["running"]        = False
            st.session_state["awaiting_submit"] = False
            st.session_state["done"]           = True

    return changed

# ── Helper: format log lines with colour ──────────────────────────────────────
def render_log_html(lines):
    html_lines = []
    for line in lines[-200:]:  # keep last 200
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

# ── Status badge HTML ──────────────────────────────────────────────────────────
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

# Header
st.markdown("""
<div class="app-header">
    <h1>🎓 Amrita Feedback Automater</h1>
    <p>Automate TLP &amp; Course feedback submissions for the Amrita Student Portal</p>
</div>
""", unsafe_allow_html=True)

# ── Step 1 ─────────────────────────────────────────────────────────────────────
st.markdown('<div class="card"><div class="card-title">Step 1 — Login &amp; Fetch</div>', unsafe_allow_html=True)

col1, col2, col3 = st.columns([3, 3, 2])
with col1:
    email = st.text_input("Amrita Email", value=tlp.OUTLOOK_EMAIL, key="email_input",
                          placeholder="you@bl.students.amrita.edu")
with col2:
    password = st.text_input("Password", type="password", key="password_input",
                             placeholder="Your Microsoft password")
with col3:
    default_rating = st.selectbox("Default Rating", RATING_OPTIONS, index=1, key="default_rating")

col4, col5 = st.columns([3, 2])
with col4:
    mode = st.radio("Feedback Mode", ["TLP Feedback", "Course Feedback"],
                    horizontal=True, key="mode_radio")
with col5:
    fetch_clicked = st.button(
        "🔍 Fetch Subjects",
        disabled=st.session_state["running"],
        key="fetch_btn"
    )

st.markdown("</div>", unsafe_allow_html=True)

# Fetch handler
if fetch_clicked:
    if not email or not password:
        st.error("Please enter both Email and Password.")
    else:
        st.session_state["subjects"]         = []
        st.session_state["log_lines"]        = []
        st.session_state["done"]             = False
        st.session_state["awaiting_submit"]  = False
        st.session_state["running"]          = True
        st.session_state["user_config_queue"] = queue.Queue()

        mode_key = "tlp" if mode == "TLP Feedback" else "course"
        default_idx = parse_rating(default_rating)

        # Capture queues as local vars — threads cannot access st.session_state
        _ui_q  = st.session_state["ui_queue"]
        _ucq   = st.session_state["user_config_queue"]

        t = threading.Thread(
            target=run_asyncio_loop,
            args=(email, password, default_idx, mode_key, _ui_q, _ucq),
            daemon=True,
        )
        t.start()
        st.rerun()

# ── Step 2 ─────────────────────────────────────────────────────────────────────
st.markdown('<div class="card"><div class="card-title">Step 2 — Assign Ratings &amp; Submit</div>', unsafe_allow_html=True)

subjects = st.session_state["subjects"]

if not subjects:
    st.markdown('<p style="color:#4a5568;font-size:.85rem;text-align:center;padding:24px 0;">No subjects fetched yet. Click "Fetch Subjects" above.</p>', unsafe_allow_html=True)
else:
    # Header row
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
            disabled = s["status"] in ("processing", "done", "failed") or not st.session_state["awaiting_submit"]
            new_rating = st.selectbox(
                label="rating",
                options=RATING_OPTIONS,
                index=RATING_OPTIONS.index(s["rating"]) if s["rating"] in RATING_OPTIONS else 1,
                key=f"rating_{i}",
                label_visibility="collapsed",
                disabled=disabled,
            )
            subjects[i]["rating"] = new_rating
        with c4:
            st.markdown(STATUS_BADGE.get(s["status"], ""), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    submit_clicked = st.button(
        "🚀 Submit All Feedbacks",
        disabled=not st.session_state["awaiting_submit"],
        key="submit_btn",
    )

    if submit_clicked and st.session_state["awaiting_submit"]:
        config = {}
        for s in subjects:
            config[s["info"]] = parse_rating(s["rating"])
        st.session_state["user_config_queue"].put(config)
        st.session_state["awaiting_submit"] = False
        tlp.logger.info("GUI: Ratings locked in. Resuming bot execution...")
        st.rerun()

st.markdown("</div>", unsafe_allow_html=True)

# ── Activity Log ───────────────────────────────────────────────────────────────
st.markdown('<div class="card"><div class="card-title">📋 Activity Log</div>', unsafe_allow_html=True)

log_html = render_log_html(st.session_state["log_lines"])
st.markdown(log_html, unsafe_allow_html=True)

if st.session_state["done"]:
    st.success("🎉 Automation complete! All feedbacks have been processed.")

st.markdown("</div>", unsafe_allow_html=True)

# ── Auto-rerun while bot is running ───────────────────────────────────────────
if st.session_state["running"]:
    time.sleep(0.8)
    st.rerun()
