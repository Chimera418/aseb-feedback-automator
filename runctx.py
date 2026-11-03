"""
Per-run isolation for multi-user hosting.

Every bot run happens on its own thread, so the thread identity is used as the
run key. This keeps two things from leaking between concurrent users:

  * log records  — routed to the queue belonging to the thread that emitted them
  * screenshots  — written under images/<run_id>/ instead of a shared filename

When nothing is registered (CLI use, gui.py), everything falls back to the
plain shared behaviour it had before.
"""

import logging
import os
import threading
import uuid

_LOCK = threading.Lock()
_QUEUES: dict[int, object] = {}   # thread ident -> ui queue
_RUN_IDS: dict[int, str] = {}     # thread ident -> run id


# ── Run registration ──────────────────────────────────────────────────────────
def register(ui_queue=None) -> str:
    """Bind the calling thread to a fresh run id (and optionally a log queue)."""
    ident = threading.get_ident()
    run_id = uuid.uuid4().hex[:12]
    with _LOCK:
        _RUN_IDS[ident] = run_id
        if ui_queue is not None:
            _QUEUES[ident] = ui_queue
    return run_id


def unregister() -> None:
    """Release the calling thread's binding. Safe to call twice."""
    ident = threading.get_ident()
    with _LOCK:
        _QUEUES.pop(ident, None)
        _RUN_IDS.pop(ident, None)


def current_run_id() -> str:
    with _LOCK:
        return _RUN_IDS.get(threading.get_ident(), "local")


# ── Screenshots ───────────────────────────────────────────────────────────────
def shot(name: str) -> str:
    """Path for a screenshot, scoped to the current run."""
    run_id = current_run_id()
    directory = os.path.join("images", run_id) if run_id != "local" else "images"
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, name)


def purge(run_id: str) -> None:
    """Delete a finished run's screenshots. Best effort — never raises."""
    if not run_id or run_id == "local":
        return
    directory = os.path.join("images", run_id)
    try:
        for entry in os.listdir(directory):
            os.remove(os.path.join(directory, entry))
        os.rmdir(directory)
    except OSError:
        pass


# ── Log routing ───────────────────────────────────────────────────────────────
class _Router(logging.Handler):
    """Delivers each record only to the queue owned by its originating thread."""

    def __init__(self):
        super().__init__()
        self.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
        )

    def emit(self, record):
        with _LOCK:
            q = _QUEUES.get(record.thread)
        if q is None:
            return  # no owner listening — drop rather than broadcast
        try:
            q.put(("log", self.format(record)))
        except Exception:
            pass


_router = None


def install(*loggers) -> None:
    """Attach the single process-wide router to each logger. Idempotent."""
    global _router
    if _router is None:
        _router = _Router()
    for lgr in loggers:
        if not any(h.__class__.__name__ == "_Router" for h in lgr.handlers):
            lgr.addHandler(_router)
        lgr.setLevel(logging.INFO)
