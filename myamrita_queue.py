#!/usr/bin/env python3
"""
MyAmrita Queue & Chaining Orchestrator

Handles:
1. Chaining Course + TLP (or TLP + Course) for a single student.
2. Sequential queue processing across multiple students (Student A -> Student B -> ...),
   where each student can have Course, TLP, or Both (Course + TLP) executed automatically.
"""

import asyncio
import logging
from typing import List, Dict, Any, Callable, Optional

import tlp
import course

logger = logging.getLogger(__name__)


def normalize_email(email_or_roll: str) -> str:
    """Ensures input is a valid student email; appends domain if only roll number given."""
    s = (email_or_roll or "").strip()
    if not s:
        return ""
    if "@" not in s:
        return f"{s}@bl.students.amrita.edu"
    return s


async def run_single_chained(
    email: str,
    password: str,
    mode: str = "both",  # 'course', 'tlp', 'both'
    answer_idx: int = 1,
    headless: bool = True,
    progress_callback: Optional[Callable] = None,
    cancel_queue=None,
    user_config_queue=None,
) -> None:
    """
    Executes Course, TLP, or Both sequentially for a single student.
    """
    norm_email = normalize_email(email)
    logger.info("==========================================")
    logger.info(f"🚀 STARTING MYAMRITA EXECUTION: {mode.upper()}")
    logger.info(f"📧 Student: {norm_email}")
    logger.info(f"🎯 Default Rating Scheme: {answer_idx}")
    logger.info("==========================================")

    def check_cancelled() -> bool:
        if cancel_queue and not cancel_queue.empty():
            try:
                msg = cancel_queue.get_nowait()
                if msg == "CANCEL":
                    return True
                cancel_queue.put_nowait(msg)
            except Exception:
                pass
        return False

    # 1. Course Feedback Phase
    if mode in ("course", "both"):
        if check_cancelled():
            logger.info("🚫 Operation cancelled before Course Feedback.")
            return

        logger.info(f"\n📚 [Phase 1] Launching Course Feedback for {norm_email}...")
        if progress_callback:
            progress_callback("chain_phase", {"phase": "course", "label": "Course Feedback"})

        try:
            await course.run(
                email=norm_email,
                password=password,
                answer_idx=answer_idx,
                headless=headless,
                progress_callback=progress_callback,
                user_config_queue=user_config_queue,
            )
            logger.info(f"✅ Course Feedback phase completed for {norm_email}.")
        except Exception as e:
            logger.error(f"❌ Course Feedback encountered an error: {e}")
            if mode == "course":
                raise

    # 2. TLP Feedback Phase
    if mode in ("tlp", "both"):
        if check_cancelled():
            logger.info("🚫 Operation cancelled before TLP Feedback.")
            return

        logger.info(f"\n📋 [Phase 2] Launching TLP Feedback for {norm_email}...")
        if progress_callback:
            progress_callback("chain_phase", {"phase": "tlp", "label": "TLP Feedback"})

        try:
            await tlp.run(
                email=norm_email,
                password=password,
                answer_idx=answer_idx,
                headless=headless,
                progress_callback=progress_callback,
                user_config_queue=user_config_queue,
            )
            logger.info(f"✅ TLP Feedback phase completed for {norm_email}.")
        except Exception as e:
            logger.error(f"❌ TLP Feedback encountered an error: {e}")
            if mode == "tlp":
                raise

    logger.info(f"\n🎉 ✅ All requested MyAmrita feedback finished for {norm_email}!\n")


async def run_queue(
    queue_items: List[Dict[str, Any]],
    delay_between_students: float = 2.0,
    headless: bool = True,
    progress_callback: Optional[Callable] = None,
    cancel_queue=None,
) -> Dict[str, Any]:
    """
    Processes a sequential queue of MyAmrita student submissions.
    Each item in queue_items must be a dict:
      {
        "email": str,
        "password": str,
        "mode": str ("both", "course", "tlp"),
        "answer_idx": int (0 to 4)
      }
    """
    total = len(queue_items)
    logger.info("==========================================")
    logger.info("🚀 STARTING MYAMRITA QUEUE SUBMISSION")
    logger.info(f"👥 Total Students Queued: {total}")
    logger.info(f"⏱ Delay Between Students: {delay_between_students}s")
    logger.info("==========================================\n")

    stats = {
        "total": total,
        "success": 0,
        "failed": 0,
        "processed": 0,
        "cancelled": False,
    }

    if progress_callback:
        progress_callback("queue_start", {"total": total, "stats": dict(stats)})

    if total == 0:
        logger.info("Queue is empty.")
        if progress_callback:
            progress_callback("queue_complete", stats)
        return stats

    for idx, item in enumerate(queue_items, start=1):
        # Cancellation check before this student starts
        if cancel_queue and not cancel_queue.empty():
            try:
                msg = cancel_queue.get_nowait()
                if msg == "CANCEL":
                    logger.info("🚫 Queue execution stopped by user.")
                    stats["cancelled"] = True
                    break
                cancel_queue.put_nowait(msg)
            except Exception:
                pass

        raw_email = item.get("email", "").strip()
        email = normalize_email(raw_email)
        password = item.get("password", "").strip()
        student_mode = item.get("mode", "both").lower()
        answer_idx = item.get("answer_idx", 1)

        if not email or not password:
            logger.warning(f"⚠️ [{idx}/{total}] Skipping invalid queue item: email/password missing.")
            stats["failed"] += 1
            stats["processed"] += 1
            continue

        mode_label = "Both (Course + TLP)" if student_mode == "both" else ("Course Feedback" if student_mode == "course" else "TLP Feedback")
        logger.info(f"\n[{idx}/{total}] 🎓 Processing student: {email} | Mode: {mode_label}")

        if progress_callback:
            progress_callback("queue_student_start", {
                "index": idx,
                "total": total,
                "email": email,
                "mode": student_mode,
                "mode_label": mode_label,
            })

        student_failed = False
        error_msg = ""

        try:
            # Phase 1: Course if requested
            if student_mode in ("both", "course"):
                if progress_callback:
                    progress_callback("queue_student_step", {
                        "email": email,
                        "step": "course",
                        "status": "📚 Running Course Feedback...",
                    })
                logger.info(f"   ▶️ Running Course Feedback for {email}...")
                await course.run(
                    email=email,
                    password=password,
                    answer_idx=answer_idx,
                    headless=headless,
                    progress_callback=lambda etype, data: progress_callback("course_" + etype, data) if progress_callback else None,
                    user_config_queue=None,  # Automated submission using answer_idx
                )

            # Check cancellation between phases
            if cancel_queue and not cancel_queue.empty():
                try:
                    msg = cancel_queue.get_nowait()
                    if msg == "CANCEL":
                        logger.info("🚫 Queue execution stopped by user.")
                        stats["cancelled"] = True
                        break
                    cancel_queue.put_nowait(msg)
                except Exception:
                    pass

            # Phase 2: TLP if requested
            if student_mode in ("both", "tlp"):
                if progress_callback:
                    progress_callback("queue_student_step", {
                        "email": email,
                        "step": "tlp",
                        "status": "📋 Running TLP Feedback...",
                    })
                logger.info(f"   ▶️ Running TLP Feedback for {email}...")
                await tlp.run(
                    email=email,
                    password=password,
                    answer_idx=answer_idx,
                    headless=headless,
                    progress_callback=lambda etype, data: progress_callback("tlp_" + etype, data) if progress_callback else None,
                    user_config_queue=None,  # Automated submission using answer_idx
                )

        except Exception as e:
            student_failed = True
            error_msg = str(e)
            logger.error(f"   ❌ Execution failed for {email}: {error_msg}")

        stats["processed"] += 1
        if student_failed:
            stats["failed"] += 1
            if progress_callback:
                progress_callback("queue_student_failed", {
                    "email": email,
                    "error": error_msg,
                    "stats": dict(stats),
                })
        else:
            stats["success"] += 1
            logger.info(f"   ✅ Done: All feedbacks successfully submitted for {email}.")
            if progress_callback:
                progress_callback("queue_student_done", {
                    "email": email,
                    "stats": dict(stats),
                })

        # Inter-student delay (if more students remain)
        if idx < total and not stats["cancelled"]:
            logger.info(f"⏳ Waiting {delay_between_students}s before next student...")
            await asyncio.sleep(delay_between_students)

    logger.info("==========================================")
    logger.info("🎉 MYAMRITA QUEUE PROCESSING COMPLETE!")
    logger.info(f"📊 Total: {stats['total']} | ✅ Success: {stats['success']} | ❌ Failed: {stats['failed']}")
    logger.info("==========================================\n")

    if progress_callback:
        progress_callback("queue_complete", stats)

    return stats
