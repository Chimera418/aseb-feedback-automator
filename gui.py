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
import tlp  # our main script
import course  # course feedback script
import vidya  # amritavidya (web-blr) feedback script

class TextHandler(logging.Handler):
    def __init__(self, text_widget):
        logging.Handler.__init__(self)
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record)
        def append():
            self.text_widget.configure(state='normal')
            self.text_widget.insert(tk.END, msg + '\n')
            self.text_widget.configure(state='disabled')
            self.text_widget.yview(tk.END)
        self.text_widget.after(0, append)

class FeedbackGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("MyAmrita TLP Feedback Automater")
        self.root.geometry("850x650")
        
        self.ui_queue = queue.Queue()
        self.user_config_queue = queue.Queue()
        self.subject_widgets = {} # info -> {'status_label': lbl, 'rating_var': var}
        
        self.create_widgets()
        self.setup_logging()
        self.setup_audio()

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
        except:
            pass

    def setup_logging(self):
        text_handler = TextHandler(self.log_text)
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
        text_handler.setFormatter(formatter)
        tlp.logger.addHandler(text_handler)
        tlp.logger.setLevel(logging.INFO)
        course.logger.addHandler(text_handler)
        course.logger.setLevel(logging.INFO)
        vidya.logger.addHandler(text_handler)
        vidya.logger.setLevel(logging.INFO)

    def create_widgets(self):
        # --- Top Frame: Credentials ---
        input_frame = ttk.LabelFrame(self.root, text="Step 1: Login & Fetch", padding=(10, 10))
        input_frame.pack(fill=tk.X, padx=10, pady=5)

        self.email_label = ttk.Label(input_frame, text="Amrita Email:")
        self.email_label.grid(row=0, column=0, sticky=tk.W, pady=2)
        self.email_var = tk.StringVar(value=tlp.OUTLOOK_EMAIL)
        self.email_entry = ttk.Entry(input_frame, textvariable=self.email_var, width=40)
        self.email_entry.grid(row=0, column=1, sticky=tk.W, pady=2, padx=5)

        ttk.Label(input_frame, text="Password:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.password_var = tk.StringVar()
        self.password_entry = ttk.Entry(input_frame, textvariable=self.password_var, show="*", width=40)
        self.password_entry.grid(row=1, column=1, sticky=tk.W, pady=2, padx=5)

        ttk.Label(input_frame, text="Default Rating:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.rating_var = tk.StringVar()
        self.rating_cb = ttk.Combobox(input_frame, textvariable=self.rating_var, state="readonly", width=37)
        self.rating_cb['values'] = ("Excellent (0)", "Very Good (1)", "Good (2)", "Satisfactory (3)", "Poor (4)")
        self.rating_cb.current(1)
        self.rating_cb.grid(row=2, column=1, sticky=tk.W, pady=2, padx=5)
        
        ttk.Label(input_frame, text="Feedback Mode:").grid(row=3, column=0, sticky=tk.W, pady=2)
        mode_frame = ttk.Frame(input_frame)
        mode_frame.grid(row=3, column=1, sticky=tk.W, pady=2)
        
        self.mode_var = tk.StringVar(value="tlp")
        ttk.Radiobutton(mode_frame, text="TLP Feedback", variable=self.mode_var, value="tlp",
                        command=self.on_mode_change).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(mode_frame, text="Course Feedback", variable=self.mode_var, value="course",
                        command=self.on_mode_change).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(mode_frame, text="AmritaVidya Feedback", variable=self.mode_var, value="vidya",
                        command=self.on_mode_change).pack(side=tk.LEFT)

        self.fetch_btn = ttk.Button(input_frame, text="🔍 Fetch Subjects", command=self.start_fetching)
        self.fetch_btn.grid(row=0, column=2, rowspan=5, padx=20, ipadx=10, ipady=10)

        # --- Audio Frame ---
        audio_frame = ttk.Frame(input_frame)
        audio_frame.grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        ttk.Label(audio_frame, text="Volume:").pack(side=tk.LEFT, padx=(0, 10))
        self.volume_scale = ttk.Scale(audio_frame, from_=0, to=1, orient=tk.HORIZONTAL, value=0.5, command=self.change_volume)
        self.volume_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # --- Middle Frame: Dynamic Subjects List ---
        list_frame = ttk.LabelFrame(self.root, text="Step 2: Assign Ratings", padding=(10, 10))
        list_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=5)

        # Scrollable canvas for subjects
        canvas = tk.Canvas(list_frame, height=150)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        self.subjects_inner_frame = ttk.Frame(canvas)

        self.subjects_inner_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.subjects_inner_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.submit_btn = ttk.Button(list_frame, text="🚀 Submit All Feedbacks", command=self.confirm_ratings, state=tk.DISABLED)
        self.submit_btn.pack(side=tk.BOTTOM, pady=10, ipadx=10, ipady=5)

        # --- Bottom Frame: Logs ---
        log_frame = ttk.LabelFrame(self.root, text="Activity Log", padding=(10, 10))
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.log_text = tk.Text(log_frame, state='disabled', wrap='word', height=10)
        log_scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def on_mode_change(self):
        if self.mode_var.get() == "vidya":
            self.email_label.config(text="Vidya Username:")
            self.email_var.set(vidya.VIDYA_USERNAME)
        else:
            self.email_label.config(text="Amrita Email:")
            self.email_var.set(tlp.OUTLOOK_EMAIL)

    def parse_rating(self, rating_str):
        try:
            return int(rating_str.split('(')[1].split(')')[0])
        except Exception:
            return 1

    def start_fetching(self):
        email = self.email_var.get().strip()
        password = self.password_var.get()
        default_rating_idx = self.parse_rating(self.rating_var.get())

        mode = self.mode_var.get()
        if not email or (not password and mode != "vidya"):
            messagebox.showerror("Missing Info", "Please enter both Email and Password.")
            return

        self.fetch_btn.config(state=tk.DISABLED)
        
        # Clear existing subjects
        for widget in self.subjects_inner_frame.winfo_children():
            widget.destroy()
        self.subject_widgets.clear()
        
        tlp.logger.info(f"GUI: Starting background browser thread ({mode.upper()} Mode) to fetch subjects...")

        thread = threading.Thread(
            target=self.run_asyncio_loop,
            args=(email, password, default_rating_idx, mode),
            daemon=True
        )
        thread.start()
        
        self.root.after(100, self.process_queue)

    def run_asyncio_loop(self, email, password, default_idx, mode):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            module_to_run = {"tlp": tlp, "course": course, "vidya": vidya}[mode]
            loop.run_until_complete(
                module_to_run.run(
                    email=email,
                    password=password,
                    answer_idx=default_idx,
                    headless=True,
                    progress_callback=self.handle_progress,
                    user_config_queue=self.user_config_queue
                )
            )
        except Exception as e:
            tlp.logger.error(f"Fatal error in automation loop: {e}")
        finally:
            loop.close()
            self.ui_queue.put(("thread_done", None))

    def handle_progress(self, event_type, data):
        self.ui_queue.put((event_type, data))

    def process_queue(self):
        try:
            while True:
                event_type, data = self.ui_queue.get_nowait()
                
                if event_type == "waiting_for_user":
                    # data = list of pending feedbacks
                    for item in data:
                        info = item["info"]
                        parts = info.split(' | ')
                        course = parts[0][:50] + "..." if len(parts[0]) > 50 else parts[0]
                        faculty = parts[1] if len(parts) > 1 else ""
                        
                        row_frame = ttk.Frame(self.subjects_inner_frame)
                        row_frame.pack(fill=tk.X, pady=2, padx=5)
                        
                        ttk.Label(row_frame, text=course, width=40, anchor="w").pack(side=tk.LEFT, padx=5)
                        ttk.Label(row_frame, text=faculty, width=25, anchor="w").pack(side=tk.LEFT, padx=5)
                        
                        cb_var = tk.StringVar(value=self.rating_var.get())
                        cb = ttk.Combobox(row_frame, textvariable=cb_var, state="readonly", width=15)
                        cb['values'] = ("Excellent (0)", "Very Good (1)", "Good (2)", "Satisfactory (3)", "Poor (4)")
                        cb.pack(side=tk.LEFT, padx=5)
                        
                        status_lbl = ttk.Label(row_frame, text="⏳ Pending", width=15, anchor="w")
                        status_lbl.pack(side=tk.LEFT, padx=5)
                        
                        self.subject_widgets[info] = {'status_label': status_lbl, 'rating_var': cb_var, 'cb': cb}

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
                    self.fetch_btn.config(state=tk.NORMAL)
                    self.submit_btn.config(state=tk.DISABLED)
                    tlp.logger.info("GUI: Automation completely finished.")
                    messagebox.showinfo("Done", "Automation has completed!")
                    
        except queue.Empty:
            pass
            
        if str(self.fetch_btn['state']) == tk.DISABLED:
            self.root.after(100, self.process_queue)

    def confirm_ratings(self):
        # Collect configurations from the GUI
        config = {}
        for info, widgets in self.subject_widgets.items():
            rating_str = widgets['rating_var'].get()
            config[info] = self.parse_rating(rating_str)
            # Disable comboboxes to show it's locked in
            widgets['cb'].config(state=tk.DISABLED)

        # Send it to the asyncio thread
        self.submit_btn.config(state=tk.DISABLED)
        tlp.logger.info("GUI: Ratings locked in. Resuming bot execution...")
        self.user_config_queue.put(config)


if __name__ == "__main__":
    root = tk.Tk()
    app = FeedbackGUI(root)
    root.mainloop()
