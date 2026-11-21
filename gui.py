import os
os.makedirs("logs", exist_ok=True)
os.makedirs("images", exist_ok=True)

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import asyncio
import logging
import queue
import pygame
import tlp     # TLP feedback script
import course  # Course feedback script
import vidya   # AmritaVidya (web-blr) feedback script
import myamrita_queue  # Multi-student queue and Course+TLP chaining

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

SINGLE_RATING_OPTIONS = [
    "Excellent (0)",
    "Very Good (1)",
    "Good (2)",
    "Satisfactory (3)",
    "Poor (4)",
]

class TextHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record)
        def append():
            try:
                self.text_widget.configure(state='normal')
                self.text_widget.insert(tk.END, msg + '\n')
                self.text_widget.configure(state='disabled')
                self.text_widget.yview(tk.END)
            except Exception:
                pass
        try:
            self.text_widget.after(0, append)
        except Exception:
            pass

class FeedbackGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("MyAmrita Feedback Automater")
        self.root.geometry("920x740")
        self.root.minsize(860, 680)
        
        self.ui_queue = queue.Queue()
        self.user_config_queue = queue.Queue()
        self.subject_widgets = {}  # info -> {'status_label': lbl, 'rating_var': var, 'cb': cb}
        self.batch_tree_items = {} # username -> tree_item_id
        self.queue_tree_items = {} # email -> tree_item_id
        self.myamrita_queue_items = []
        self.is_queue_running = False
        
        self.run_id = 0
        self.is_fetching = False
        self.is_submitting = False
        self.awaiting_submit = False
        self.is_batch_running = False
        self.done = False
        self.student_name = ""
        
        self.create_widgets()
        self.setup_logging()
        self.setup_audio()
        self.update_submode_visibility()

    def setup_audio(self):
        try:
            pygame.mixer.init()
            audio_file = os.path.join("misc", "Furinkazan -Tsuki Sayu Yoru-.mp3")
            if os.path.exists(audio_file):
                pygame.mixer.music.load(audio_file)
                pygame.mixer.music.set_volume(0.5)
                pygame.mixer.music.play(loops=-1)
            else:
                tlp.logger.warning(f"Audio file not found: {audio_file}")
        except Exception as e:
            tlp.logger.error(f"Failed to initialize audio: {e}")

    def change_volume(self, val):
        try:
            pygame.mixer.music.set_volume(float(val))
        except Exception:
            pass

    def setup_logging(self):
        text_handler = TextHandler(self.log_text)
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
        text_handler.setFormatter(formatter)
        for lgr in (tlp.logger, course.logger, vidya.logger, myamrita_queue.logger):
            lgr.addHandler(text_handler)
            lgr.setLevel(logging.INFO)

    def create_widgets(self):
        # ── Mode Selection Header ──────────────────────────────────────────────
        header_frame = ttk.LabelFrame(self.root, text="Portal & Execution Mode", padding=(10, 8))
        header_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(header_frame, text="Feedback Portal:").grid(row=0, column=0, sticky=tk.W, pady=2)
        mode_btn_frame = ttk.Frame(header_frame)
        mode_btn_frame.grid(row=0, column=1, sticky=tk.W, pady=2, padx=5)

        self.mode_var = tk.StringVar(value="tlp")
        ttk.Radiobutton(mode_btn_frame, text="TLP Feedback", variable=self.mode_var, value="tlp",
                        command=self.on_mode_change).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(mode_btn_frame, text="Course Feedback", variable=self.mode_var, value="course",
                        command=self.on_mode_change).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(mode_btn_frame, text="🔄 Both (Course + TLP)", variable=self.mode_var, value="both",
                        command=self.on_mode_change).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(mode_btn_frame, text="AmritaVidya Feedback", variable=self.mode_var, value="vidya",
                        command=self.on_mode_change).pack(side=tk.LEFT)

        # Execution Submode (Single vs Batch/Queue)
        self.submode_lbl = ttk.Label(header_frame, text="Execution Mode:")
        self.submode_frame = ttk.Frame(header_frame)
        self.submode_var = tk.StringVar(value="single")
        self.submode_single_rb = ttk.Radiobutton(self.submode_frame, text="👤 Single Student", variable=self.submode_var, value="single",
                        command=self.on_submode_change)
        self.submode_single_rb.pack(side=tk.LEFT, padx=(0, 15))
        self.submode_multi_rb = ttk.Radiobutton(self.submode_frame, text="⚡ Queue Mode (Multiple Students / Tasks)", variable=self.submode_var, value="multi",
                        command=self.on_submode_change)
        self.submode_multi_rb.pack(side=tk.LEFT)

        # ── Single Student Container ──────────────────────────────────────────
        self.single_container = ttk.Frame(self.root)

        # Single Student Step 1: Credentials
        single_input_frame = ttk.LabelFrame(self.single_container, text="Step 1: Student Login & Fetch", padding=(10, 10))
        single_input_frame.pack(fill=tk.X, pady=(0, 5))

        self.email_label = ttk.Label(single_input_frame, text="Amrita Email:")
        self.email_label.grid(row=0, column=0, sticky=tk.W, pady=2)
        self.email_var = tk.StringVar(value=tlp.OUTLOOK_EMAIL)
        self.email_entry = ttk.Entry(single_input_frame, textvariable=self.email_var, width=38)
        self.email_entry.grid(row=0, column=1, sticky=tk.W, pady=2, padx=5)

        ttk.Label(single_input_frame, text="Password:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.password_var = tk.StringVar()
        self.password_entry = ttk.Entry(single_input_frame, textvariable=self.password_var, show="*", width=38)
        self.password_entry.grid(row=1, column=1, sticky=tk.W, pady=2, padx=5)

        ttk.Label(single_input_frame, text="Default Rating:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.rating_var = tk.StringVar()
        self.rating_cb = ttk.Combobox(single_input_frame, textvariable=self.rating_var, state="readonly", width=35)
        self.rating_cb['values'] = SINGLE_RATING_OPTIONS
        self.rating_cb.current(1)
        self.rating_cb.grid(row=2, column=1, sticky=tk.W, pady=2, padx=5)
        self.rating_cb.bind("<<ComboboxSelected>>", lambda e: self.on_default_rating_change())

        # Action Buttons Box for Single Mode
        btn_box = ttk.Frame(single_input_frame)
        btn_box.grid(row=0, column=2, rowspan=3, padx=20, pady=2)

        self.auto_run_btn = ttk.Button(btn_box, text="🚀 Run & Submit All", command=self.start_auto_run)
        self.auto_run_btn.pack(fill=tk.X, pady=(0, 4), ipadx=10, ipady=5)

        self.fetch_btn = ttk.Button(btn_box, text="🔍 Review First", command=self.start_fetching)
        self.fetch_btn.pack(fill=tk.X, pady=(0, 4), ipadx=10, ipady=3)

        self.cancel_btn = ttk.Button(btn_box, text="⏹ Cancel", command=self.cancel_action, state=tk.DISABLED)
        self.cancel_btn.pack(fill=tk.X, ipadx=10, ipady=3)

        # Audio Volume
        audio_frame = ttk.Frame(single_input_frame)
        audio_frame.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=4)
        ttk.Label(audio_frame, text="Audio Volume:").pack(side=tk.LEFT, padx=(0, 10))
        self.volume_scale = ttk.Scale(audio_frame, from_=0, to=1, orient=tk.HORIZONTAL, value=0.5, command=self.change_volume)
        self.volume_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Single Student Step 2: Subject Review & Submit
        self.single_list_frame = ttk.LabelFrame(self.single_container, text="Step 2: Assign Ratings & Submit", padding=(10, 10))
        self.single_list_frame.pack(fill=tk.BOTH, expand=False, pady=5)

        # Quick Set All Bar
        quick_set_frame = ttk.Frame(self.single_list_frame)
        quick_set_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 6))

        ttk.Label(quick_set_frame, text="⚡ Set All Subjects To:").pack(side=tk.LEFT, padx=(0, 5))
        self.set_all_rating_var = tk.StringVar(value=SINGLE_RATING_OPTIONS[1])
        self.set_all_rating_cb = ttk.Combobox(quick_set_frame, textvariable=self.set_all_rating_var, state="readonly", width=18)
        self.set_all_rating_cb['values'] = SINGLE_RATING_OPTIONS
        self.set_all_rating_cb.pack(side=tk.LEFT, padx=(0, 6))

        ttk.Button(quick_set_frame, text="⚡ Apply to All Subjects", command=self.apply_rating_to_all_subjects).pack(side=tk.LEFT)

        canvas = tk.Canvas(self.single_list_frame, height=140)
        scrollbar = ttk.Scrollbar(self.single_list_frame, orient="vertical", command=canvas.yview)
        self.subjects_inner_frame = ttk.Frame(canvas)
        self.subjects_inner_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.subjects_inner_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.submit_btn = ttk.Button(self.single_list_frame, text="🚀 Submit All Feedbacks", command=self.confirm_ratings, state=tk.DISABLED)
        self.submit_btn.pack(side=tk.BOTTOM, pady=6, ipadx=10, ipady=4)

        # ── Batch Mode Container (AmritaVidya Only) ───────────────────────────
        self.batch_container = ttk.Frame(self.root)

        # Batch Step 1: Input & Range Generator
        batch_input_frame = ttk.LabelFrame(self.batch_container, text="AmritaVidya Batch Setup — Roll Numbers & Credentials", padding=(10, 8))
        batch_input_frame.pack(fill=tk.X, pady=(0, 5))

        # Range Generator Row
        range_frame = ttk.Frame(batch_input_frame)
        range_frame.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(range_frame, text="Range Generator:").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Label(range_frame, text="Prefix:").pack(side=tk.LEFT, padx=(4, 2))
        self.batch_prefix_var = tk.StringVar(value="bl.sc.u4aie24")
        self.batch_prefix_entry = ttk.Entry(range_frame, textvariable=self.batch_prefix_var, width=15)
        self.batch_prefix_entry.pack(side=tk.LEFT, padx=2)

        ttk.Label(range_frame, text="Start:").pack(side=tk.LEFT, padx=(6, 2))
        self.batch_start_var = tk.StringVar(value="101")
        self.batch_start_entry = ttk.Entry(range_frame, textvariable=self.batch_start_var, width=6)
        self.batch_start_entry.pack(side=tk.LEFT, padx=2)

        ttk.Label(range_frame, text="End:").pack(side=tk.LEFT, padx=(6, 2))
        self.batch_end_var = tk.StringVar(value="160")
        self.batch_end_entry = ttk.Entry(range_frame, textvariable=self.batch_end_var, width=6)
        self.batch_end_entry.pack(side=tk.LEFT, padx=2)

        ttk.Button(range_frame, text="➕ Add Range", command=self.generate_batch_range).pack(side=tk.LEFT, padx=8)
        ttk.Button(range_frame, text="🗑 Clear List", command=self.clear_batch_list).pack(side=tk.LEFT, padx=2)

        # Text Area for Roll Numbers
        text_row_frame = ttk.Frame(batch_input_frame)
        text_row_frame.pack(fill=tk.X, pady=2)

        left_text_col = ttk.Frame(text_row_frame)
        left_text_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.batch_count_lbl = ttk.Label(left_text_col, text="Student Roll Numbers (0 queued):", font=("Segoe UI", 9, "bold"))
        self.batch_count_lbl.pack(anchor="w", pady=(0, 2))

        text_scroll_frame = ttk.Frame(left_text_col)
        text_scroll_frame.pack(fill=tk.BOTH, expand=True)
        self.batch_text = tk.Text(text_scroll_frame, height=5, width=40, font=("Consolas", 9))
        self.batch_text_scroll = ttk.Scrollbar(text_scroll_frame, command=self.batch_text.yview)
        self.batch_text.configure(yscrollcommand=self.batch_text_scroll.set)
        self.batch_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.batch_text_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.batch_text.bind("<KeyRelease>", lambda e: self.update_batch_count())

        ttk.Label(left_text_col, text="Format: one roll number per line (e.g. bl.sc.u4aie24101 or roll,password)",
                  font=("Segoe UI", 8), foreground="#666").pack(anchor="w", pady=(2, 0))

        # Batch Settings (Right Column)
        right_cfg_col = ttk.Frame(text_row_frame)
        right_cfg_col.pack(side=tk.RIGHT, fill=tk.Y, padx=(15, 5))

        ttk.Label(right_cfg_col, text="Default Password:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.batch_pass_var = tk.StringVar(value="amma")
        self.batch_pass_entry = ttk.Entry(right_cfg_col, textvariable=self.batch_pass_var, width=28)
        self.batch_pass_entry.grid(row=0, column=1, sticky=tk.W, pady=2, padx=4)

        ttk.Label(right_cfg_col, text="Rating Scheme:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.batch_rating_var = tk.StringVar(value=BATCH_RATING_OPTIONS[0])
        self.batch_rating_cb = ttk.Combobox(right_cfg_col, textvariable=self.batch_rating_var, state="readonly", width=26)
        self.batch_rating_cb['values'] = BATCH_RATING_OPTIONS
        self.batch_rating_cb.grid(row=1, column=1, sticky=tk.W, pady=2, padx=4)

        ttk.Label(right_cfg_col, text="Delay (seconds):").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.batch_delay_var = tk.DoubleVar(value=1.5)
        self.batch_delay_sp = ttk.Spinbox(right_cfg_col, from_=0.0, to=10.0, increment=0.5, textvariable=self.batch_delay_var, width=10)
        self.batch_delay_sp.grid(row=2, column=1, sticky=tk.W, pady=2, padx=4)

        batch_btn_box = ttk.Frame(right_cfg_col)
        batch_btn_box.grid(row=3, column=0, columnspan=2, sticky=tk.EW, pady=(8, 0))
        self.batch_start_btn = ttk.Button(batch_btn_box, text="🚀 Start Batch Submission", command=self.start_batch_submission)
        self.batch_start_btn.pack(fill=tk.X, pady=(0, 4), ipady=5)
        self.batch_cancel_btn = ttk.Button(batch_btn_box, text="⏹ Cancel Batch", command=self.cancel_batch_action, state=tk.DISABLED)
        self.batch_cancel_btn.pack(fill=tk.X, ipady=3)

        # Batch Step 2: Progress Table & Summary
        self.batch_list_frame = ttk.LabelFrame(self.batch_container, text="Batch Submission Progress", padding=(10, 8))
        self.batch_list_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        tree_frame = ttk.Frame(self.batch_list_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("num", "roll", "name", "pending", "status")
        self.batch_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=8)
        self.batch_tree.heading("num", text="#")
        self.batch_tree.heading("roll", text="Roll Number")
        self.batch_tree.heading("name", text="Student Name")
        self.batch_tree.heading("pending", text="Feedbacks")
        self.batch_tree.heading("status", text="Status")

        self.batch_tree.column("num", width=35, anchor="center")
        self.batch_tree.column("roll", width=160, anchor="w")
        self.batch_tree.column("name", width=180, anchor="w")
        self.batch_tree.column("pending", width=90, anchor="center")
        self.batch_tree.column("status", width=220, anchor="w")

        tree_scroll_y = ttk.Scrollbar(tree_frame, orient="vertical", command=self.batch_tree.yview)
        self.batch_tree.configure(yscrollcommand=tree_scroll_y.set)
        self.batch_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        self.batch_progress_bar = ttk.Progressbar(self.batch_list_frame, mode="determinate")
        self.batch_progress_bar.pack(fill=tk.X, pady=(6, 2))

        self.batch_summary_lbl = ttk.Label(self.batch_list_frame, text="Ready. Add student roll numbers above and click 'Start Batch Submission'.",
                                           font=("Segoe UI", 9, "bold"))
        self.batch_summary_lbl.pack(anchor="w", pady=(2, 0))

        # ── MyAmrita Queue Container (TLP / Course / Both Multi-Student) ─────
        self.queue_container = ttk.Frame(self.root)

        # Setup Frame
        q_setup_frame = ttk.LabelFrame(self.queue_container, text="MyAmrita Queue Setup — Multi-Student & Task Queue", padding=(10, 8))
        q_setup_frame.pack(fill=tk.X, pady=(0, 5))

        # Row 1: Single Student Quick Add
        q_add_row = ttk.Frame(q_setup_frame)
        q_add_row.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(q_add_row, text="Email / Roll:").pack(side=tk.LEFT, padx=(0, 2))
        self.q_email_var = tk.StringVar(value="")
        self.q_email_entry = ttk.Entry(q_add_row, textvariable=self.q_email_var, width=28)
        self.q_email_entry.pack(side=tk.LEFT, padx=2)

        ttk.Label(q_add_row, text="Password:").pack(side=tk.LEFT, padx=(6, 2))
        self.q_pass_var = tk.StringVar(value="")
        self.q_pass_entry = ttk.Entry(q_add_row, textvariable=self.q_pass_var, show="*", width=14)
        self.q_pass_entry.pack(side=tk.LEFT, padx=2)

        ttk.Label(q_add_row, text="Mode:").pack(side=tk.LEFT, padx=(6, 2))
        self.q_mode_var = tk.StringVar(value="Both (Course + TLP)")
        self.q_mode_cb = ttk.Combobox(q_add_row, textvariable=self.q_mode_var, state="readonly", width=18)
        self.q_mode_cb['values'] = ["Both (Course + TLP)", "Course Feedback", "TLP Feedback"]
        self.q_mode_cb.pack(side=tk.LEFT, padx=2)

        ttk.Label(q_add_row, text="Rating:").pack(side=tk.LEFT, padx=(6, 2))
        self.q_rating_var = tk.StringVar(value="Very Good (1)")
        self.q_rating_cb = ttk.Combobox(q_add_row, textvariable=self.q_rating_var, state="readonly", width=13)
        self.q_rating_cb['values'] = SINGLE_RATING_OPTIONS
        self.q_rating_cb.pack(side=tk.LEFT, padx=2)

        ttk.Button(q_add_row, text="➕ Add to Queue", command=self.add_single_to_queue).pack(side=tk.LEFT, padx=8)

        # Row 2: Bulk Add from text
        q_bulk_row = ttk.Frame(q_setup_frame)
        q_bulk_row.pack(fill=tk.X, pady=2)

        q_bulk_left = ttk.Frame(q_bulk_row)
        q_bulk_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.q_count_lbl = ttk.Label(q_bulk_left, text="Bulk Add (paste one per line: roll,password or email,password):", font=("Segoe UI", 8))
        self.q_count_lbl.pack(anchor="w")

        q_txt_scroll_f = ttk.Frame(q_bulk_left)
        q_txt_scroll_f.pack(fill=tk.BOTH, expand=True, pady=2)
        self.q_bulk_text = tk.Text(q_txt_scroll_f, height=3, width=40, font=("Consolas", 9))
        self.q_bulk_scroll = ttk.Scrollbar(q_txt_scroll_f, command=self.q_bulk_text.yview)
        self.q_bulk_text.configure(yscrollcommand=self.q_bulk_scroll.set)
        self.q_bulk_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.q_bulk_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        q_bulk_right = ttk.Frame(q_bulk_row)
        q_bulk_right.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 5))

        ttk.Button(q_bulk_right, text="📋 Queue All from Text", command=self.add_bulk_to_queue).pack(fill=tk.X, pady=1)
        ttk.Button(q_bulk_right, text="🗑 Clear Queue", command=self.clear_queue).pack(fill=tk.X, pady=1)

        # Queue Progress & Table Frame
        self.queue_list_frame = ttk.LabelFrame(self.queue_container, text="Queue Execution Progress", padding=(10, 8))
        self.queue_list_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        q_tree_frame = ttk.Frame(self.queue_list_frame)
        q_tree_frame.pack(fill=tk.BOTH, expand=True)

        q_columns = ("num", "email", "mode", "rating", "status")
        self.queue_tree = ttk.Treeview(q_tree_frame, columns=q_columns, show="headings", height=7)
        self.queue_tree.heading("num", text="#")
        self.queue_tree.heading("email", text="Student Email")
        self.queue_tree.heading("mode", text="Mode")
        self.queue_tree.heading("rating", text="Rating")
        self.queue_tree.heading("status", text="Status")

        self.queue_tree.column("num", width=35, anchor="center")
        self.queue_tree.column("email", width=250, anchor="w")
        self.queue_tree.column("mode", width=160, anchor="center")
        self.queue_tree.column("rating", width=110, anchor="center")
        self.queue_tree.column("status", width=220, anchor="w")

        q_tree_scroll_y = ttk.Scrollbar(q_tree_frame, orient="vertical", command=self.queue_tree.yview)
        self.queue_tree.configure(yscrollcommand=q_tree_scroll_y.set)
        self.queue_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        q_tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        # Rating modification row for queue
        q_rating_mod_row = ttk.Frame(self.queue_list_frame)
        q_rating_mod_row.pack(fill=tk.X, pady=(4, 2))

        ttk.Label(q_rating_mod_row, text="Change Rating for Queue:").pack(side=tk.LEFT, padx=(0, 5))
        self.q_edit_rating_var = tk.StringVar(value=SINGLE_RATING_OPTIONS[1])
        self.q_edit_rating_cb = ttk.Combobox(q_rating_mod_row, textvariable=self.q_edit_rating_var, state="readonly", width=18)
        self.q_edit_rating_cb['values'] = SINGLE_RATING_OPTIONS
        self.q_edit_rating_cb.pack(side=tk.LEFT, padx=(0, 6))

        ttk.Button(q_rating_mod_row, text="✏️ Update Selected", command=self.update_selected_queue_rating).pack(side=tk.LEFT, padx=2)
        ttk.Button(q_rating_mod_row, text="⚡ Apply to All in Queue", command=self.update_all_queue_ratings).pack(side=tk.LEFT, padx=2)

        # Controls & Progress
        q_ctrl_row = ttk.Frame(self.queue_list_frame)
        q_ctrl_row.pack(fill=tk.X, pady=(6, 2))

        self.queue_start_btn = ttk.Button(q_ctrl_row, text="🚀 Start Queue Execution", command=self.start_queue_execution)
        self.queue_start_btn.pack(side=tk.LEFT, padx=(0, 8), ipadx=8, ipady=3)

        self.queue_cancel_btn = ttk.Button(q_ctrl_row, text="⏹ Stop Queue", command=self.cancel_queue_action, state=tk.DISABLED)
        self.queue_cancel_btn.pack(side=tk.LEFT, padx=4, ipadx=6, ipady=3)

        ttk.Label(q_ctrl_row, text="Delay (sec):").pack(side=tk.LEFT, padx=(15, 2))
        self.q_delay_var = tk.DoubleVar(value=2.0)
        self.q_delay_sp = ttk.Spinbox(q_ctrl_row, from_=0.0, to=10.0, increment=0.5, textvariable=self.q_delay_var, width=6)
        self.q_delay_sp.pack(side=tk.LEFT, padx=2)

        self.queue_progress_bar = ttk.Progressbar(self.queue_list_frame, mode="determinate")
        self.queue_progress_bar.pack(fill=tk.X, pady=(6, 2))

        self.queue_summary_lbl = ttk.Label(self.queue_list_frame, text="Queue is empty. Add students above and click 'Start Queue Execution'.", font=("Segoe UI", 9, "bold"))
        self.queue_summary_lbl.pack(anchor="w", pady=(2, 0))

        # ── Bottom Frame: Shared Activity Log ─────────────────────────────────
        self.log_frame = ttk.LabelFrame(self.root, text="Activity Log", padding=(10, 8))
        self.log_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.log_text = tk.Text(self.log_frame, state='disabled', wrap='word', height=7, font=("Consolas", 9))
        log_scrollbar = ttk.Scrollbar(self.log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def on_mode_change(self):
        mode = self.mode_var.get()
        if mode == "vidya":
            self.email_label.config(text="Vidya Username:")
            self.email_var.set(vidya.VIDYA_USERNAME)
            self.fetch_btn.config(text="🔍 Fetch Subjects")
        elif mode == "both":
            self.email_label.config(text="Amrita Email:")
            self.email_var.set(tlp.OUTLOOK_EMAIL)
            self.fetch_btn.config(text="🚀 Run Both (Course + TLP)")
        else:
            self.email_label.config(text="Amrita Email:")
            self.email_var.set(tlp.OUTLOOK_EMAIL)
            self.fetch_btn.config(text="🔍 Fetch Subjects")

        # Cancel any active single-mode task
        if self.awaiting_submit:
            try:
                self.user_config_queue.put_nowait("CANCEL")
            except Exception:
                pass
            self.run_id += 1
            self.awaiting_submit = False
            self.is_fetching = False
            self.is_submitting = False
            for widget in self.subjects_inner_frame.winfo_children():
                widget.destroy()
            self.subject_widgets.clear()
            self.cancel_btn.config(state=tk.DISABLED)
            self.submit_btn.config(state=tk.DISABLED)

        self.update_submode_visibility()

    def on_submode_change(self):
        self.update_submode_visibility()

    def update_submode_visibility(self):
        mode = self.mode_var.get()
        submode = self.submode_var.get()

        self.submode_lbl.grid(row=1, column=0, sticky=tk.W, pady=2)
        self.submode_frame.grid(row=1, column=1, sticky=tk.W, pady=2, padx=5)

        if mode == "vidya":
            self.submode_lbl.config(text="AmritaVidya Mode:")
            self.submode_multi_rb.config(text="⚡ Batch Submit Mode (Multiple Students)")
            if submode == "multi":
                self.single_container.pack_forget()
                self.queue_container.pack_forget()
                self.batch_container.pack(side=tk.TOP, fill=tk.BOTH, expand=False, padx=10, pady=5, before=self.log_frame)
            else:
                self.batch_container.pack_forget()
                self.queue_container.pack_forget()
                self.single_container.pack(side=tk.TOP, fill=tk.BOTH, expand=False, padx=10, pady=5, before=self.log_frame)
        else:
            self.submode_lbl.config(text="MyAmrita Mode:")
            self.submode_multi_rb.config(text="⚡ Queue Mode (Multiple Students / Tasks)")
            if submode == "multi":
                self.single_container.pack_forget()
                self.batch_container.pack_forget()
                self.queue_container.pack(side=tk.TOP, fill=tk.BOTH, expand=False, padx=10, pady=5, before=self.log_frame)
            else:
                self.batch_container.pack_forget()
                self.queue_container.pack_forget()
                self.single_container.pack(side=tk.TOP, fill=tk.BOTH, expand=False, padx=10, pady=5, before=self.log_frame)

    def generate_batch_range(self):
        prefix = self.batch_prefix_var.get().strip()
        start_str = self.batch_start_var.get().strip()
        end_str = self.batch_end_var.get().strip()

        if not start_str.isdigit() or not end_str.isdigit():
            messagebox.showerror("Invalid Range", "Start and End roll numbers must be positive integers.")
            return

        start_num = int(start_str)
        end_num = int(end_str)
        if start_num > end_num:
            messagebox.showerror("Invalid Range", "Start roll number cannot be greater than End roll number.")
            return

        pad = max(len(start_str), len(end_str))
        generated = [f"{prefix}{str(i).zfill(pad)}" for i in range(start_num, end_num + 1)]
        existing = self.batch_text.get("1.0", tk.END).strip()
        if existing:
            new_text = existing + "\n" + "\n".join(generated) + "\n"
        else:
            new_text = "\n".join(generated) + "\n"

        self.batch_text.delete("1.0", tk.END)
        self.batch_text.insert(tk.END, new_text)
        self.update_batch_count()

    def clear_batch_list(self):
        self.batch_text.delete("1.0", tk.END)
        self.update_batch_count()

    def update_batch_count(self):
        raw_lines = self.batch_text.get("1.0", tk.END).strip().splitlines()
        students = [l.strip() for l in raw_lines if l.strip() and not l.strip().startswith("#")]
        # Deduplicate while preserving order
        unique_students = list(dict.fromkeys(students))
        self.batch_count_lbl.config(text=f"Student Roll Numbers ({len(unique_students)} queued):")

    def parse_rating(self, rating_val):
        if isinstance(rating_val, int):
            return rating_val
        try:
            s = str(rating_val)
            if '(' in s and ')' in s:
                return int(s.split('(')[1].split(')')[0])
            return int(s.strip())
        except Exception:
            return 1

    def on_default_rating_change(self):
        val = self.rating_var.get()
        if hasattr(self, "set_all_rating_var"):
            self.set_all_rating_var.set(val)
        for info, widgets in self.subject_widgets.items():
            if widgets.get("cb") and str(widgets["cb"].cget("state")) != "disabled":
                widgets["rating_var"].set(val)

    def apply_rating_to_all_subjects(self):
        new_val = self.set_all_rating_var.get()
        for info, widgets in self.subject_widgets.items():
            if widgets.get("cb") and str(widgets["cb"].cget("state")) != "disabled":
                widgets["rating_var"].set(new_val)

    def update_selected_queue_rating(self):
        sel = self.queue_tree.selection()
        if not sel:
            messagebox.showinfo("Select Student", "Please click on a student in the queue table first.")
            return
        new_rating_str = self.q_edit_rating_var.get()
        new_idx = self.parse_rating(new_rating_str)
        for item_id in sel:
            curr_vals = list(self.queue_tree.item(item_id, "values"))
            if len(curr_vals) >= 4:
                curr_vals[3] = new_rating_str
                self.queue_tree.item(item_id, values=curr_vals)
                email = curr_vals[1]
                for it in self.myamrita_queue_items:
                    if it["email"] == email:
                        it["rating_str"] = new_rating_str
                        it["answer_idx"] = new_idx

    def update_all_queue_ratings(self):
        if not self.myamrita_queue_items:
            messagebox.showinfo("Queue Empty", "No students currently in queue.")
            return
        new_rating_str = self.q_edit_rating_var.get()
        new_idx = self.parse_rating(new_rating_str)
        for it in self.myamrita_queue_items:
            it["rating_str"] = new_rating_str
            it["answer_idx"] = new_idx
        for item_id in self.queue_tree.get_children():
            curr_vals = list(self.queue_tree.item(item_id, "values"))
            if len(curr_vals) >= 4:
                curr_vals[3] = new_rating_str
                self.queue_tree.item(item_id, values=curr_vals)

    # ── Single Student Actions ────────────────────────────────────────────────
    def cancel_action(self):
        try:
            self.user_config_queue.put_nowait("CANCEL")
        except Exception:
            pass
        self.run_id += 1
        self.is_fetching = False
        self.is_submitting = False
        self.awaiting_submit = False
        self.auto_run_btn.config(state=tk.NORMAL, text="🚀 Run & Submit All")
        self.fetch_btn.config(state=tk.NORMAL, text="🔍 Review First")
        self.cancel_btn.config(state=tk.DISABLED)
        self.submit_btn.config(state=tk.DISABLED)
        tlp.logger.info("GUI: 🛑 Operation cancelled by user.")

    def start_auto_run(self):
        email = self.email_var.get().strip()
        password = self.password_var.get()
        default_rating_idx = self.parse_rating(self.rating_var.get())

        mode = self.mode_var.get()
        if not email or (not password and mode != "vidya"):
            messagebox.showerror("Missing Info", "Please enter both Email and Password.")
            return

        if self.awaiting_submit:
            try:
                self.user_config_queue.put_nowait("CANCEL")
            except Exception:
                pass

        self.run_id += 1
        current_run_id = self.run_id
        self.user_config_queue = queue.Queue()
        self.is_fetching = False
        self.is_submitting = True
        self.awaiting_submit = False
        self.done = False

        self.auto_run_btn.config(state=tk.DISABLED, text="🚀 Running...")
        self.fetch_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)
        self.submit_btn.config(state=tk.DISABLED)

        for widget in self.subjects_inner_frame.winfo_children():
            widget.destroy()
        self.subject_widgets.clear()

        tlp.logger.info(f"GUI: Starting fully automated run ({mode.upper()} Mode) with rating scheme {default_rating_idx}...")

        thread = threading.Thread(
            target=self.run_asyncio_loop,
            args=(current_run_id, email, password, default_rating_idx, mode, None, True),
            daemon=True
        )
        thread.start()
        self.root.after(100, self.process_queue)

    def start_fetching(self):
        email = self.email_var.get().strip()
        password = self.password_var.get()
        default_rating_idx = self.parse_rating(self.rating_var.get())

        mode = self.mode_var.get()
        if not email or (not password and mode != "vidya"):
            messagebox.showerror("Missing Info", "Please enter both Email and Password.")
            return

        if self.awaiting_submit:
            try:
                self.user_config_queue.put_nowait("CANCEL")
            except Exception:
                pass

        self.run_id += 1
        current_run_id = self.run_id
        self.user_config_queue = queue.Queue()
        self.is_fetching = True
        self.is_submitting = False
        self.awaiting_submit = False
        self.done = False

        self.auto_run_btn.config(state=tk.DISABLED)
        self.fetch_btn.config(state=tk.DISABLED, text="⏳ Fetching...")
        self.cancel_btn.config(state=tk.NORMAL)
        self.submit_btn.config(state=tk.DISABLED)

        for widget in self.subjects_inner_frame.winfo_children():
            widget.destroy()
        self.subject_widgets.clear()

        tlp.logger.info(f"GUI: Starting background browser thread ({mode.upper()} Mode) to fetch subjects...")

        thread = threading.Thread(
            target=self.run_asyncio_loop,
            args=(current_run_id, email, password, default_rating_idx, mode, self.user_config_queue, False),
            daemon=True
        )
        thread.start()
        self.root.after(100, self.process_queue)

    def run_asyncio_loop(self, run_id, email, password, default_idx, mode, user_config_queue, auto_submit=False):
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
                        progress_callback=lambda etype, data: self.handle_progress(run_id, etype, data),
                        user_config_queue=user_config_queue,
                        auto_submit=auto_submit,
                    )
                )
            else:
                module_to_run = {"tlp": tlp, "course": course, "vidya": vidya}[mode]
                effective_q = None if auto_submit else user_config_queue
                loop.run_until_complete(
                    module_to_run.run(
                        email=email,
                        password=password,
                        answer_idx=default_idx,
                        headless=True,
                        progress_callback=lambda etype, data: self.handle_progress(run_id, etype, data),
                        user_config_queue=effective_q
                    )
                )
        except Exception as e:
            tlp.logger.error(f"Fatal error in automation loop: {e}")
        finally:
            try:
                loop.close()
            except Exception:
                pass
            self.ui_queue.put((run_id, "thread_done", None))

    def confirm_ratings(self):
        config = {}
        for info, widgets in self.subject_widgets.items():
            rating_str = widgets['rating_var'].get()
            config[info] = self.parse_rating(rating_str)
            widgets['cb'].config(state=tk.DISABLED)

        self.awaiting_submit = False
        self.is_submitting = True
        self.fetch_btn.config(state=tk.DISABLED)
        self.submit_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)
        tlp.logger.info("GUI: Ratings locked in. Resuming bot execution...")
        self.user_config_queue.put(config)

    # ── MyAmrita Queue Actions ────────────────────────────────────────────────
    def add_single_to_queue(self):
        email_or_roll = self.q_email_var.get().strip()
        pwd = self.q_pass_var.get().strip()
        if not email_or_roll or not pwd:
            messagebox.showerror("Missing Information", "Please enter Email/Roll Number and Password.")
            return

        mode_choice = self.q_mode_var.get()
        if "Both" in mode_choice:
            mode_key = "both"
        elif "Course" in mode_choice:
            mode_key = "course"
        else:
            mode_key = "tlp"

        rating_str = self.q_rating_var.get()
        answer_idx = self.parse_rating(rating_str)
        norm_email = myamrita_queue.normalize_email(email_or_roll)

        item = {
            "email": norm_email,
            "password": pwd,
            "mode": mode_key,
            "mode_label": mode_choice,
            "answer_idx": answer_idx,
            "rating_str": rating_str,
            "status": "⏳ Queued",
        }
        self.myamrita_queue_items.append(item)
        idx = len(self.myamrita_queue_items)
        row_id = self.queue_tree.insert("", tk.END, values=(idx, norm_email, mode_choice, rating_str, "⏳ Queued"))
        self.queue_tree_items[norm_email] = row_id

        self.q_email_var.set("")
        self.q_pass_var.set("")
        self.queue_summary_lbl.config(text=f"{len(self.myamrita_queue_items)} student(s) in queue. Click 'Start Queue Execution' to begin.")

    def add_bulk_to_queue(self):
        raw = self.q_bulk_text.get("1.0", tk.END).strip().splitlines()
        default_pwd = self.q_pass_var.get().strip() or "amma"
        mode_choice = self.q_mode_var.get()
        if "Both" in mode_choice:
            mode_key = "both"
        elif "Course" in mode_choice:
            mode_key = "course"
        else:
            mode_key = "tlp"

        rating_str = self.q_rating_var.get()
        answer_idx = self.parse_rating(rating_str)

        added = 0
        for line in raw:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.replace(":", ",").split(",") if p.strip()]
            user = parts[0]
            pwd = parts[1] if len(parts) > 1 else default_pwd
            norm_email = myamrita_queue.normalize_email(user)
            if not norm_email or not pwd:
                continue

            item = {
                "email": norm_email,
                "password": pwd,
                "mode": mode_key,
                "mode_label": mode_choice,
                "answer_idx": answer_idx,
                "rating_str": rating_str,
                "status": "⏳ Queued",
            }
            self.myamrita_queue_items.append(item)
            idx = len(self.myamrita_queue_items)
            row_id = self.queue_tree.insert("", tk.END, values=(idx, norm_email, mode_choice, rating_str, "⏳ Queued"))
            self.queue_tree_items[norm_email] = row_id
            added += 1

        self.q_bulk_text.delete("1.0", tk.END)
        self.queue_summary_lbl.config(text=f"{len(self.myamrita_queue_items)} student(s) in queue. Click 'Start Queue Execution' to begin.")

    def clear_queue(self):
        self.myamrita_queue_items.clear()
        self.queue_tree_items.clear()
        for item in self.queue_tree.get_children():
            self.queue_tree.delete(item)
        self.queue_summary_lbl.config(text="Queue cleared.")

    def start_queue_execution(self):
        if not self.myamrita_queue_items:
            messagebox.showerror("Empty Queue", "No students queued! Add student roll numbers/emails above.")
            return

        self.run_id += 1
        current_run_id = self.run_id
        self.is_queue_running = True
        self.user_config_queue = queue.Queue()

        self.queue_start_btn.config(state=tk.DISABLED)
        self.queue_cancel_btn.config(state=tk.NORMAL)
        self.queue_progress_bar["maximum"] = len(self.myamrita_queue_items)
        self.queue_progress_bar["value"] = 0

        for em, row_id in self.queue_tree_items.items():
            self.queue_tree.set(row_id, "status", "⏳ Queued")

        try:
            delay_sec = float(self.q_delay_var.get())
        except Exception:
            delay_sec = 2.0

        items_copy = list(self.myamrita_queue_items)
        tlp.logger.info(f"GUI: Launching MyAmrita Queue Execution for {len(items_copy)} students...")

        thread = threading.Thread(
            target=self.run_asyncio_queue_loop,
            args=(current_run_id, items_copy, delay_sec, self.user_config_queue),
            daemon=True
        )
        thread.start()
        self.root.after(100, self.process_queue)

    def cancel_queue_action(self):
        try:
            self.user_config_queue.put_nowait("CANCEL")
        except Exception:
            pass
        self.queue_summary_lbl.config(text="Stopping queue after current student finishes...")
        tlp.logger.info("GUI: 🛑 Stopping MyAmrita Queue execution...")

    def run_asyncio_queue_loop(self, run_id, queue_items, delay_sec, cancel_queue):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                myamrita_queue.run_queue(
                    queue_items=queue_items,
                    delay_between_students=delay_sec,
                    headless=True,
                    progress_callback=lambda etype, data: self.handle_progress(run_id, etype, data),
                    cancel_queue=cancel_queue
                )
            )
        except Exception as e:
            tlp.logger.error(f"Fatal error in queue loop: {e}")
        finally:
            try:
                loop.close()
            except Exception:
                pass
            self.ui_queue.put((run_id, "queue_thread_done", None))

    # ── Batch Mode Actions ────────────────────────────────────────────────────
    def start_batch_submission(self):
        raw_lines = self.batch_text.get("1.0", tk.END).strip().splitlines()
        default_pass = self.batch_pass_var.get().strip() or "amma"
        rating_scheme = self.batch_rating_var.get()
        try:
            delay_sec = float(self.batch_delay_var.get())
        except Exception:
            delay_sec = 1.5

        students = []
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
            pwd = parts[1] if len(parts) > 1 else default_pass
            students.append({"username": user, "password": pwd})

        if not students:
            messagebox.showwarning("No Students", "Please enter or generate at least one student roll number.")
            return

        self.run_id += 1
        current_run_id = self.run_id
        self.is_batch_running = True
        self.user_config_queue = queue.Queue()

        self.batch_start_btn.config(state=tk.DISABLED)
        self.batch_cancel_btn.config(state=tk.NORMAL)

        # Clear and populate Treeview
        for item in self.batch_tree.get_children():
            self.batch_tree.delete(item)

        self.batch_tree_items.clear()
        for i, s in enumerate(students, start=1):
            item_id = self.batch_tree.insert("", tk.END, values=(i, s["username"], "—", "—", "⏳ Queued"))
            self.batch_tree_items[s["username"]] = item_id

        self.batch_progress_bar["maximum"] = len(students)
        self.batch_progress_bar["value"] = 0
        self.batch_summary_lbl.config(text=f"Batch queued: {len(students)} students | Scheme: {rating_scheme}")

        tlp.logger.info(f"GUI: Launching AmritaVidya Batch Submission for {len(students)} students...")

        thread = threading.Thread(
            target=self.run_asyncio_batch_loop,
            args=(current_run_id, students, rating_scheme, delay_sec, self.user_config_queue),
            daemon=True
        )
        thread.start()
        self.root.after(100, self.process_queue)

    def cancel_batch_action(self):
        try:
            self.user_config_queue.put_nowait("CANCEL")
        except Exception:
            pass
        self.batch_summary_lbl.config(text="Stopping batch after current student finishes...")
        tlp.logger.info("GUI: 🛑 Cancelling batch submission...")

    def run_asyncio_batch_loop(self, run_id, students, rating_scheme, delay_sec, cancel_queue):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                vidya.run_batch(
                    students=students,
                    answer_idx=rating_scheme,
                    delay_between_students=delay_sec,
                    headless=True,
                    progress_callback=lambda etype, data: self.handle_progress(run_id, etype, data),
                    cancel_queue=cancel_queue
                )
            )
        except Exception as e:
            tlp.logger.error(f"Fatal error in batch loop: {e}")
        finally:
            try:
                loop.close()
            except Exception:
                pass
            self.ui_queue.put((run_id, "batch_thread_done", None))

    def update_batch_summary_stats(self, stats, finished=False):
        if not stats:
            return
        tot = stats.get("total", 0)
        done_cnt = stats.get("success", 0)
        skip_cnt = stats.get("skipped", 0)
        fail_cnt = stats.get("failed", 0)
        proc_cnt = stats.get("processed", 0)
        self.batch_progress_bar["value"] = proc_cnt

        status_text = f"Progress: {proc_cnt}/{tot} | ✅ Submitted: {done_cnt} | ⚪ Already Done: {skip_cnt} | ❌ Failed: {fail_cnt}"
        if finished:
            status_text = f"Complete! " + status_text
        self.batch_summary_lbl.config(text=status_text)

    # ── Progress and Event Queue Handler ──────────────────────────────────────
    def handle_progress(self, run_id, event_type, data):
        self.ui_queue.put((run_id, event_type, data))

    def process_queue(self):
        try:
            while True:
                item = self.ui_queue.get_nowait()
                if len(item) == 3:
                    event_run_id, event_type, data = item
                    if event_run_id != self.run_id:
                        continue
                elif len(item) == 2:
                    event_type, data = item
                else:
                    continue

                # ── Single Mode Events ────────────────────────────────────────
                if event_type == "student_name":
                    if data:
                        self.student_name = data
                        self.root.title(f"MyAmrita Feedback Automater — Welcome, {data}")

                elif event_type == "waiting_for_user":
                    for w in self.subjects_inner_frame.winfo_children():
                        w.destroy()
                    self.subject_widgets.clear()
                    for item_data in data:
                        info = item_data["info"]
                        parts = info.split(' | ')
                        course_name = parts[0][:50] + "..." if len(parts[0]) > 50 else parts[0]
                        faculty = parts[1] if len(parts) > 1 else ""

                        row_frame = ttk.Frame(self.subjects_inner_frame)
                        row_frame.pack(fill=tk.X, pady=2, padx=5)

                        ttk.Label(row_frame, text=course_name, width=40, anchor="w").pack(side=tk.LEFT, padx=5)
                        ttk.Label(row_frame, text=faculty, width=25, anchor="w").pack(side=tk.LEFT, padx=5)

                        cb_var = tk.StringVar(value=self.rating_var.get())
                        cb = ttk.Combobox(row_frame, textvariable=cb_var, state="readonly", width=15)
                        cb['values'] = SINGLE_RATING_OPTIONS
                        cb.pack(side=tk.LEFT, padx=5)

                        status_lbl = ttk.Label(row_frame, text="⏳ Pending", width=15, anchor="w")
                        status_lbl.pack(side=tk.LEFT, padx=5)

                        self.subject_widgets[info] = {'status_label': status_lbl, 'rating_var': cb_var, 'cb': cb}

                    self.is_fetching = False
                    self.awaiting_submit = True
                    self.fetch_btn.config(state=tk.NORMAL, text="🔄 Re-fetch Subjects")
                    self.cancel_btn.config(state=tk.NORMAL)
                    self.submit_btn.config(state=tk.NORMAL)
                    tlp.logger.info("GUI: Please assign ratings for each subject and click Submit.")

                elif event_type == "subject_processing":
                    if data in self.subject_widgets:
                        self.subject_widgets[data]['status_label'].config(text="🔄 Processing...", foreground="blue")

                elif event_type == "subject_done":
                    if data in self.subject_widgets:
                        self.subject_widgets[data]['status_label'].config(text="✅ Done", foreground="green")

                elif event_type == "subject_failed":
                    if data in self.subject_widgets:
                        self.subject_widgets[data]['status_label'].config(text="❌ Failed", foreground="red")

                elif event_type == "thread_done":
                    was_submitting = self.is_submitting
                    was_fetching = self.is_fetching
                    self.is_fetching = False
                    self.is_submitting = False

                    self.auto_run_btn.config(state=tk.NORMAL, text="🚀 Run & Submit All")
                    self.fetch_btn.config(state=tk.NORMAL, text="🔄 Review First" if self.subject_widgets else "🔍 Review First")
                    self.cancel_btn.config(state=tk.DISABLED)
                    self.submit_btn.config(state=tk.DISABLED)

                    if was_submitting:
                        self.done = True
                        self.awaiting_submit = False
                        tlp.logger.info("GUI: Automation completely finished.")
                        messagebox.showinfo("Done", "Automation has completed! All feedbacks submitted.")
                    elif was_fetching and not self.awaiting_submit:
                        self.done = True
                        tlp.logger.info("GUI: No pending feedbacks found or fetch ended.")
                        if not self.subject_widgets:
                            messagebox.showinfo("Info", "No pending feedbacks found! You're all set.")

                # ── Batch Mode Events ─────────────────────────────────────────
                elif event_type == "batch_student_start":
                    u = data["username"]
                    idx = data["index"]
                    tot = data["total"]
                    if u in self.batch_tree_items:
                        item_id = self.batch_tree_items[u]
                        self.batch_tree.set(item_id, "status", "🔐 Logging in...")
                        self.batch_tree.see(item_id)
                    self.batch_summary_lbl.config(text=f"Processing student [{idx}/{tot}]: {u}...")

                elif event_type == "batch_student_name":
                    u = data["username"]
                    name = data["name"]
                    if u in self.batch_tree_items:
                        self.batch_tree.set(self.batch_tree_items[u], "name", name)

                elif event_type == "batch_student_pending":
                    u = data["username"]
                    count = data["pending_count"]
                    if u in self.batch_tree_items:
                        item_id = self.batch_tree_items[u]
                        self.batch_tree.set(item_id, "pending", f"{count} pending")
                        self.batch_tree.set(item_id, "status", f"📝 Submitting (0/{count})...")

                elif event_type == "batch_student_submitting":
                    u = data["username"]
                    curr = data["current"]
                    tot = data["total"]
                    if u in self.batch_tree_items:
                        item_id = self.batch_tree_items[u]
                        self.batch_tree.set(item_id, "status", f"📝 Submitting ({curr}/{tot})...")

                elif event_type == "batch_student_done":
                    u = data["username"]
                    cnt = data["submitted_count"]
                    stats = data.get("stats", {})
                    if u in self.batch_tree_items:
                        self.batch_tree.set(self.batch_tree_items[u], "status", f"✅ Done ({cnt} submitted)")
                    self.update_batch_summary_stats(stats)

                elif event_type == "batch_student_skipped":
                    u = data["username"]
                    stats = data.get("stats", {})
                    if u in self.batch_tree_items:
                        item_id = self.batch_tree_items[u]
                        self.batch_tree.set(item_id, "pending", "0")
                        self.batch_tree.set(item_id, "status", "⚪ Already Done")
                    self.update_batch_summary_stats(stats)

                elif event_type == "batch_student_failed":
                    u = data["username"]
                    err = data["error"]
                    stats = data.get("stats", {})
                    if u in self.batch_tree_items:
                        item_id = self.batch_tree_items[u]
                        self.batch_tree.set(item_id, "status", f"❌ Failed ({err})")
                    self.update_batch_summary_stats(stats)

                elif event_type == "batch_complete":
                    stats = data
                    self.is_batch_running = False
                    self.batch_start_btn.config(state=tk.NORMAL)
                    self.batch_cancel_btn.config(state=tk.DISABLED)
                    self.update_batch_summary_stats(stats, finished=True)
                    if stats.get("cancelled"):
                        messagebox.showinfo("Cancelled", "Batch submission was cancelled by user.")
                    else:
                        messagebox.showinfo(
                            "Batch Complete",
                            f"AmritaVidya Batch Complete!\n\n"
                            f"Total Students: {stats.get('total', 0)}\n"
                            f"✅ Submitted: {stats.get('success', 0)}\n"
                            f"⚪ Already Done: {stats.get('skipped', 0)}\n"
                            f"❌ Failed: {stats.get('failed', 0)}"
                        )

                elif event_type == "batch_thread_done":
                    self.is_batch_running = False
                    self.batch_start_btn.config(state=tk.NORMAL)
                    self.batch_cancel_btn.config(state=tk.DISABLED)

                # ── MyAmrita Queue Mode Events ────────────────────────────────
                elif event_type == "queue_start":
                    tot = data.get("total", len(self.myamrita_queue_items))
                    self.queue_progress_bar["maximum"] = tot
                    self.queue_progress_bar["value"] = 0
                    self.queue_summary_lbl.config(text=f"Queue running: 0/{tot} processed...")

                elif event_type == "queue_student_start":
                    em = data["email"]
                    idx = data["index"]
                    tot = data["total"]
                    if em in self.queue_tree_items:
                        item_id = self.queue_tree_items[em]
                        self.queue_tree.set(item_id, "status", f"🔐 Starting ({data.get('mode_label', '')})...")
                        self.queue_tree.see(item_id)
                    self.queue_summary_lbl.config(text=f"Processing [{idx}/{tot}]: {em}...")

                elif event_type == "queue_student_step":
                    em = data["email"]
                    step_status = data["status"]
                    if em in self.queue_tree_items:
                        item_id = self.queue_tree_items[em]
                        self.queue_tree.set(item_id, "status", step_status)

                elif event_type == "queue_student_done":
                    em = data["email"]
                    if em in self.queue_tree_items:
                        item_id = self.queue_tree_items[em]
                        self.queue_tree.set(item_id, "status", "✅ Done")
                    stats = data.get("stats", {})
                    self.queue_progress_bar["value"] = stats.get("processed", self.queue_progress_bar["value"] + 1)
                    self.queue_summary_lbl.config(text=f"Processed {stats.get('processed', 0)}/{stats.get('total', 0)} (✅ {stats.get('success', 0)} success, ❌ {stats.get('failed', 0)} failed)")

                elif event_type == "queue_student_failed":
                    em = data["email"]
                    err = data.get("error", "Error")
                    if em in self.queue_tree_items:
                        item_id = self.queue_tree_items[em]
                        self.queue_tree.set(item_id, "status", f"❌ Failed ({err[:35]})")
                    stats = data.get("stats", {})
                    self.queue_progress_bar["value"] = stats.get("processed", self.queue_progress_bar["value"] + 1)
                    self.queue_summary_lbl.config(text=f"Processed {stats.get('processed', 0)}/{stats.get('total', 0)} (✅ {stats.get('success', 0)} success, ❌ {stats.get('failed', 0)} failed)")

                elif event_type == "queue_complete":
                    stats = data
                    self.is_queue_running = False
                    self.queue_start_btn.config(state=tk.NORMAL)
                    self.queue_cancel_btn.config(state=tk.DISABLED)
                    if stats.get("cancelled"):
                        self.queue_summary_lbl.config(text=f"Queue stopped. {stats.get('success', 0)}/{stats.get('total', 0)} completed.")
                        messagebox.showinfo("Stopped", "MyAmrita Queue was stopped by user.")
                    else:
                        self.queue_summary_lbl.config(text=f"🎉 Queue Complete! Total: {stats.get('total', 0)} | ✅ Success: {stats.get('success', 0)} | ❌ Failed: {stats.get('failed', 0)}")
                        messagebox.showinfo(
                            "Queue Complete",
                            f"MyAmrita Queue Execution Complete!\n\n"
                            f"Total Students: {stats.get('total', 0)}\n"
                            f"✅ Succeeded: {stats.get('success', 0)}\n"
                            f"❌ Failed: {stats.get('failed', 0)}"
                        )

                elif event_type == "queue_thread_done":
                    self.is_queue_running = False
                    self.queue_start_btn.config(state=tk.NORMAL)
                    self.queue_cancel_btn.config(state=tk.DISABLED)

        except queue.Empty:
            pass

        if self.is_fetching or self.is_submitting or self.awaiting_submit or self.is_batch_running or self.is_queue_running:
            self.root.after(100, self.process_queue)


if __name__ == "__main__":
    root = tk.Tk()
    app = FeedbackGUI(root)
    root.mainloop()
