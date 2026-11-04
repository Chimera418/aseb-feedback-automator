#!/usr/bin/env python3

"""
AmritaVidya (web-blr) Student Feedback System automation.

Unlike the MyAmrita portal (tlp.py / course.py) this site uses a plain
username + password form and needs no OTP. Each pending course row on
feedback_home.php links to a single-page form of radio questions plus an
optional comment box.
"""

import asyncio
import os
import getpass
import logging
import random
import runctx
from urllib.parse import urljoin

from playwright.async_api import async_playwright, Page

os.makedirs("logs", exist_ok=True)
os.makedirs("images", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/vidya_feedback_bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

ANSWER_OPTION_INDEX = int(os.environ.get("ANSWER_OPTION_INDEX", 1))
VIDYA_USERNAME = os.environ.get("VIDYA_USERNAME", "bl.sc.u4aie24103")
VIDYA_PASSWORD = os.environ.get("VIDYA_PASSWORD", "amma")
HEADLESS = os.environ.get("HEADLESS", "true").lower() in ["true", "1"]
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() in ["true", "1"]

BASE_URL = "http://web-blr.amrita.edu/amritavidya/"
LOGIN_URL = BASE_URL + "main_login.php"
FEEDBACK_URL = BASE_URL + "feedback_home.php"

CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
]

SEL = {
    "login_user": "input[name='n1']",
    "login_pass": "input[name='n2']",
    "login_submit": "input[type='image'], input[type='submit'], button[type='submit']",
    "logged_in_indicator": "a:has-text('Logout')",
    "feedback_link": "a:has-text('Enter Feedback')",
    "feedback_rows": "tr:has(a:has-text('Enter Feedback'))",
    "form_radio": "input[type='radio']",
    "form_comments": "textarea",
    "form_submit": "input[type='submit'], button[type='submit'], input[type='image']",
}


async def fetch_student_name(page: Page) -> str:
    """
    Tries to extract the logged-in student's name from the AmritaVidya portal.
    Falls back to 'Student' if not found.
    """
    CANDIDATE_SELECTORS = [
        ".student-name",
        ".user-name",
        "td b",           # AmritaVidya often shows name in a bold table cell
        "table b",
        "font b",
    ]
    for sel in CANDIDATE_SELECTORS:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                name = (await el.inner_text()).strip()
                if name and 1 < len(name) < 60:
                    return name
        except Exception:
            continue

    # Fallback: look for something like "Welcome, John Doe" in body text
    try:
        body = await page.inner_text("body")
        import re as _re
        m = _re.search(r"(?:Welcome|Hello),?\s+([A-Za-z .]{3,50})", body, _re.IGNORECASE)
        if m:
            return m.group(1).strip()
    except Exception:
        pass

    return "Student"


async def safe_goto(page: Page, url: str, timeout: int = 30000, max_retries: int = 3) -> None:
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"🔗 Navigating to {url} (Attempt {attempt}/{max_retries})")
            await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            return
        except Exception as e:
            err_str = str(e)
            logger.warning(f"⚠️ Navigation failed: {err_str}")
            if "ERR_CONNECTION_TIMED_OUT" in err_str or "Timeout" in err_str:
                logger.warning("💡 Tip: The Amrita campus portal firewall blocks foreign/cloud datacenter IPs (like Streamlit Cloud/AWS) and some VPNs. Run the app locally on home/campus Wi-Fi without VPN.")
            if attempt == max_retries:
                raise RuntimeError(f"Failed to load {url} after {max_retries} attempts. Last error: {e}")
            await asyncio.sleep(3)


async def login(page: Page, username: str, password: str) -> None:
    logger.info(f"🔐 Logging in to AmritaVidya as '{username}'...")
    await safe_goto(page, LOGIN_URL)
    await page.wait_for_selector(SEL["login_user"], timeout=20000)

    await page.fill(SEL["login_user"], username)
    await page.fill(SEL["login_pass"], password)

    await page.locator(SEL["login_submit"]).first.click(timeout=15000)
    await page.wait_for_load_state("domcontentloaded", timeout=30000)

    body = await page.inner_text("body")
    if "invalid" in body.lower() or "incorrect" in body.lower() or await page.locator(SEL["login_pass"]).count() > 0:
        await page.screenshot(path=runctx.shot("vidya_login_error.png"))
        portal_msg = next(
            (line.strip() for line in body.splitlines()
             if line.strip() and ("invalid" in line.lower() or "incorrect" in line.lower())),
            "",
        )
        detail = f" Portal said: \"{portal_msg}\"" if portal_msg else ""
        raise RuntimeError(f"Login failed for '{username}'.{detail}")

    logger.info("✅ Logged in to AmritaVidya.")


async def collect_pending(page: Page) -> list:
    await safe_goto(page, FEEDBACK_URL)
    rows = await page.locator(SEL["feedback_rows"]).all()
    logger.info(f"...Found {len(rows)} pending feedback rows.")

    pending = []
    for row in rows:
        data = await row.evaluate("""(row) => {
            const cells = Array.from(row.cells).map(c => c.innerText.trim());
            return {
                code: cells[1] || '',
                title: cells[2] || '',
                faculty: cells[3] || ''
            };
        }""")
        href = await row.locator(SEL["feedback_link"]).first.get_attribute("href")
        info = f"{data['code']} {data['title']} | {data['faculty']}".strip()
        pending.append({
            "info": info,
            "code": data["code"],
            "url": urljoin(BASE_URL, href) if href and not href.strip().lower().startswith(("#", "javascript:")) else None,
        })
    return pending


async def open_feedback_form(page: Page, item: dict) -> None:
    if item["url"]:
        await safe_goto(page, item["url"])
        return

    await safe_goto(page, FEEDBACK_URL)
    row = page.locator(f"tr:has-text('{item['code']}')").filter(has=page.locator(SEL["feedback_link"])).first
    await row.locator(SEL["feedback_link"]).first.click(timeout=15000)
    await page.wait_for_load_state("domcontentloaded", timeout=30000)


def resolve_option_index(answer_val, count: int) -> int:
    """
    Resolves answer option index for a question. Supports fixed integers or randomized styles:
    - 0: Excellent
    - 1: Very Good
    - 2: Good
    - 'random_0_1' / 'mostly excellent': 70% Excellent (0), 30% Very Good (1)
    - 'random_1_2' / 'mostly very good': 75% Very Good (1), 25% Good (2)
    - 'random_mix' / 'natural mix': 45% (0), 45% (1), 10% (2)
    """
    if isinstance(answer_val, str):
        v = answer_val.lower()
        if "mostly excellent" in v or "random_0_1" in v:
            chosen = random.choices([0, 1], weights=[70, 30])[0]
        elif "mostly very good" in v or "random_1_2" in v:
            chosen = random.choices([1, 2], weights=[75, 25])[0]
        elif "natural mix" in v or "random_mix" in v:
            chosen = random.choices([0, 1, 2], weights=[45, 45, 10])[0]
        elif "(" in answer_val and ")" in answer_val:
            try:
                chosen = int(answer_val.split("(")[1].split(")")[0])
            except Exception:
                chosen = 1
        else:
            try:
                chosen = int(answer_val)
            except Exception:
                chosen = 1
    elif isinstance(answer_val, (int, float)):
        chosen = int(answer_val)
    else:
        chosen = 1
    return max(0, min(chosen, count - 1))


async def fill_feedback(page: Page, answer_idx: any) -> None:
    await page.wait_for_selector(SEL["form_radio"], timeout=20000)

    groups = await page.evaluate("""() => {
        const counts = {};
        const order = [];
        for (const r of document.querySelectorAll("input[type=radio]")) {
            const n = r.name || '';
            if (!(n in counts)) { counts[n] = 0; order.push(n); }
            counts[n]++;
        }
        return order.map(n => [n, counts[n]]);
    }""")

    if not groups:
        raise RuntimeError("No radio question groups found on the feedback form.")
    if len(groups) == 1 and groups[0][1] > 8:
        logger.warning("⚠️ Radio buttons appear to share one name — answers may land on a single question.")

    logger.info(f"📝 Filling {len(groups)} questions with rating scheme '{answer_idx}'.")
    for name, count in groups:
        idx = resolve_option_index(answer_idx, count)
        radios = page.locator(f"input[type='radio'][name='{name}']") if name else page.locator(SEL["form_radio"])
        await radios.nth(idx).check(force=True, timeout=5000)


async def submit_feedback(page: Page, subject_num: int, dry_run: bool = False) -> None:
    if dry_run:
        path = runctx.shot(f"vidya_dryrun_subject_{subject_num}.png")
        await page.screenshot(path=path, full_page=True)
        logger.info(f"🧪 DRY RUN — form filled but NOT submitted. Screenshot: {path}")
        return

    async def handle_dialog(dialog):
        logger.info(f"...Dialog: {dialog.message}. Accepting.")
        await dialog.accept()

    page.on("dialog", handle_dialog)

    submit = page.locator(SEL["form_submit"]).last
    await submit.click(timeout=15000)
    await page.wait_for_load_state("domcontentloaded", timeout=30000)
    await page.wait_for_timeout(500)


async def verify_submitted(page: Page, code: str) -> None:
    """Re-check the feedback list — the row must no longer offer 'Enter Feedback'."""
    await safe_goto(page, FEEDBACK_URL)
    still_pending = page.locator(f"tr:has-text('{code}')").filter(has=page.locator(SEL["feedback_link"]))
    if await still_pending.count() > 0:
        raise RuntimeError(f"{code} still shows 'Enter Feedback' after submitting — it did not go through.")
    logger.info(f"✅ Feedback submitted and confirmed for {code}.")


async def run(email=None, password=None, answer_idx=None, headless=None, progress_callback=None, user_config_queue=None, dry_run=None) -> None:
    username = (email or VIDYA_USERNAME).strip()
    final_password = password or VIDYA_PASSWORD
    final_answer_idx = answer_idx if answer_idx is not None else ANSWER_OPTION_INDEX
    final_headless = headless if headless is not None else HEADLESS
    final_dry_run = dry_run if dry_run is not None else DRY_RUN

    logger.info("--- AmritaVidya Student Feedback Bot ---")
    logger.info(f"Username: {username}")
    logger.info(f"Headless Mode: {final_headless}")
    logger.info(f"Answer Scheme: {final_answer_idx}")
    if final_dry_run:
        logger.info("🧪 DRY RUN enabled — forms will be filled but never submitted.")

    if not final_password:
        final_password = getpass.getpass("Enter your AmritaVidya password: ")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=final_headless, args=CHROMIUM_ARGS)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            await login(page, username, final_password)

            # Fetch and emit student name
            student_name = await fetch_student_name(page)
            logger.info(f"👤 Logged in as: {student_name}")
            if progress_callback:
                progress_callback("student_name", student_name)

            pending = await collect_pending(page)
            total_pending = len(pending)
            logger.info(f"\n📚 Pending Feedbacks Found: {total_pending}\n")

            if progress_callback:
                progress_callback("fetch_complete", pending)

            if total_pending == 0:
                logger.info("🎉 No pending feedbacks. You're all set!")
                return

            if user_config_queue:
                logger.info("⏳ Waiting for user to confirm ratings in GUI...")
                if progress_callback:
                    progress_callback("waiting_for_user", pending)

                while user_config_queue.empty():
                    await asyncio.sleep(0.5)

                user_config = user_config_queue.get()
                if user_config == "CANCEL":
                    logger.info("🚫 Automation cancelled by user.")
                    return
            else:
                user_config = {item["info"]: final_answer_idx for item in pending}

            for idx, item in enumerate(pending, start=1):
                if user_config_queue and not user_config_queue.empty():
                    try:
                        msg = user_config_queue.get_nowait()
                        if msg == 'CANCEL':
                            logger.info('🚫 Automation cancelled by user.')
                            break
                        else:
                            user_config_queue.put_nowait(msg)
                    except Exception:
                        pass
                info = item["info"]
                logger.info(f"➡️ Processing subject {idx}/{total_pending}")
                logger.info(f"📘 Subject Details: {info}")

                if progress_callback:
                    progress_callback("subject_processing", info)

                try:
                    await open_feedback_form(page, item)
                    await fill_feedback(page, user_config.get(info, final_answer_idx))
                    await submit_feedback(page, idx, final_dry_run)
                    if not final_dry_run:
                        await verify_submitted(page, item["code"])

                    if progress_callback:
                        progress_callback("subject_done", info)

                except Exception as e:
                    logger.info(f"--- ⚠️ FAILED TO SUBMIT SUBJECT {idx} ({info}) ---")
                    logger.info(f"Error: {e}")
                    await page.screenshot(path=runctx.shot(f"vidya_failure_subject_{idx}.png"))

                    if progress_callback:
                        progress_callback("subject_failed", info)

            logger.info("\n🎉 ✅ ALL AMRITAVIDYA FEEDBACK DONE — GO TOUCH GRASS 🌿\n")

        except Exception as e:
            logger.info("--- ❌ A FATAL ERROR OCCURRED ---")
            logger.info(f"Error: {e}")
            await page.screenshot(path=runctx.shot("vidya_fatal_error.png"))

        finally:
            await browser.close()


async def run_batch(
    students: list,
    answer_idx: any = 1,
    delay_between_students: float = 2.0,
    headless: bool = None,
    progress_callback=None,
    cancel_queue=None,
    dry_run: bool = None,
) -> dict:
    """
    Executes automated feedback submissions for a batch of AmritaVidya accounts.
    Uses a fresh BrowserContext for each student to prevent session contamination.
    """
    final_headless = headless if headless is not None else HEADLESS
    final_dry_run = dry_run if dry_run is not None else DRY_RUN
    total_students = len(students)

    logger.info("==========================================")
    logger.info("🚀 STARTING AMRITAVIDYA BATCH SUBMISSION")
    logger.info(f"👥 Total Students Queued: {total_students}")
    logger.info(f"🎯 Rating Scheme: {answer_idx}")
    logger.info(f"⏱ Delay Between Students: {delay_between_students}s")
    if final_dry_run:
        logger.info("🧪 DRY RUN enabled — forms will be filled but NOT submitted.")
    logger.info("==========================================\n")

    stats = {
        "total": total_students,
        "success": 0,
        "skipped": 0,
        "failed": 0,
        "processed": 0,
        "cancelled": False,
    }

    if progress_callback:
        progress_callback("batch_start", {"total": total_students, "stats": dict(stats)})

    if total_students == 0:
        logger.info("No students provided for batch run.")
        if progress_callback:
            progress_callback("batch_complete", stats)
        return stats

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=final_headless, args=CHROMIUM_ARGS)
        try:
            for idx, student_info in enumerate(students, start=1):
                # Check user cancellation before starting this student
                if cancel_queue and not cancel_queue.empty():
                    try:
                        msg = cancel_queue.get_nowait()
                        if msg == "CANCEL":
                            logger.info("🚫 Batch automation cancelled by user.")
                            stats["cancelled"] = True
                            break
                        else:
                            cancel_queue.put_nowait(msg)
                    except Exception:
                        pass

                if isinstance(student_info, dict):
                    username = student_info.get("username", "").strip()
                    password = student_info.get("password") or VIDYA_PASSWORD
                elif isinstance(student_info, (list, tuple)):
                    username = str(student_info[0]).strip()
                    password = str(student_info[1]).strip() if len(student_info) > 1 and student_info[1] else VIDYA_PASSWORD
                else:
                    username = str(student_info).strip()
                    password = VIDYA_PASSWORD

                if not username:
                    continue

                logger.info(f"\n[{idx}/{total_students}] 🎓 Processing student: {username}")
                if progress_callback:
                    progress_callback("batch_student_start", {
                        "index": idx,
                        "total": total_students,
                        "username": username,
                    })

                context = await browser.new_context()
                page = await context.new_page()

                try:
                    # 1. Login
                    await login(page, username, password)

                    # 2. Extract Name
                    student_name = await fetch_student_name(page)
                    logger.info(f"   👤 Name: {student_name}")
                    if progress_callback:
                        progress_callback("batch_student_name", {
                            "username": username,
                            "name": student_name,
                        })

                    # 3. Collect pending feedbacks
                    pending = await collect_pending(page)
                    pending_count = len(pending)

                    if pending_count == 0:
                        logger.info(f"   🎉 {username} ({student_name}): No pending feedbacks! (Already completed)")
                        stats["skipped"] += 1
                        stats["processed"] += 1
                        if progress_callback:
                            progress_callback("batch_student_skipped", {
                                "username": username,
                                "name": student_name,
                                "message": "Already completed",
                                "stats": dict(stats),
                            })
                    else:
                        logger.info(f"   📚 Found {pending_count} pending feedbacks for {username}.")
                        if progress_callback:
                            progress_callback("batch_student_pending", {
                                "username": username,
                                "name": student_name,
                                "pending_count": pending_count,
                                "stats": dict(stats),
                            })

                        submitted_count = 0
                        cancelled_mid = False
                        for s_idx, item in enumerate(pending, start=1):
                            # Check cancellation before each subject
                            if cancel_queue and not cancel_queue.empty():
                                try:
                                    msg = cancel_queue.get_nowait()
                                    if msg == "CANCEL":
                                        logger.info("🚫 Batch automation cancelled by user mid-student.")
                                        stats["cancelled"] = True
                                        cancelled_mid = True
                                        break
                                    else:
                                        cancel_queue.put_nowait(msg)
                                except Exception:
                                    pass

                            info = item["info"]
                            logger.info(f"   ➡️ [{s_idx}/{pending_count}] Submitting: {info}")
                            if progress_callback:
                                progress_callback("batch_student_submitting", {
                                    "username": username,
                                    "current": s_idx,
                                    "total": pending_count,
                                    "info": info,
                                })

                            try:
                                await open_feedback_form(page, item)
                                await fill_feedback(page, answer_idx)
                                await submit_feedback(page, s_idx, final_dry_run)
                                if not final_dry_run:
                                    await verify_submitted(page, item["code"])
                                submitted_count += 1
                            except Exception as sub_err:
                                logger.warning(f"   ⚠️ Subject submission error on {info}: {sub_err}")

                        if cancelled_mid:
                            break

                        stats["success"] += 1
                        stats["processed"] += 1
                        logger.info(f"   ✅ {username} ({student_name}): Completed {submitted_count}/{pending_count} feedbacks.")
                        if progress_callback:
                            progress_callback("batch_student_done", {
                                "username": username,
                                "name": student_name,
                                "submitted_count": submitted_count,
                                "stats": dict(stats),
                            })

                except Exception as e:
                    stats["failed"] += 1
                    stats["processed"] += 1
                    err_msg = str(e)
                    if "Login failed" in err_msg:
                        short_err = "Login failed (wrong password?)"
                    elif "timeout" in err_msg.lower():
                        short_err = "Timeout / network issue"
                    else:
                        short_err = err_msg.split("\n")[0][:60]
                    logger.error(f"   ❌ {username} failed: {short_err}")
                    try:
                        await page.screenshot(path=runctx.shot(f"vidya_batch_{username}_error.png"))
                    except Exception:
                        pass
                    if progress_callback:
                        progress_callback("batch_student_failed", {
                            "username": username,
                            "error": short_err,
                            "stats": dict(stats),
                        })

                finally:
                    try:
                        await page.close()
                        await context.close()
                    except Exception:
                        pass

                if stats.get("cancelled"):
                    break

                # Sleep delay between students
                if delay_between_students > 0 and idx < total_students:
                    await asyncio.sleep(delay_between_students)

        finally:
            await browser.close()

    logger.info("\n==========================================")
    if stats["cancelled"]:
        logger.info("🛑 BATCH SUBMISSION CANCELLED BY USER")
    else:
        logger.info("🎉 BATCH SUBMISSION COMPLETE!")
    logger.info(f"📊 Total: {stats['total']} | ✅ Done: {stats['success']} | ⚪ Already Done: {stats['skipped']} | ❌ Failed: {stats['failed']}")
    logger.info("==========================================\n")

    if progress_callback:
        progress_callback("batch_complete", stats)

    return stats


if __name__ == "__main__":
    import sys

    cli_dry_run = "--dry-run" in sys.argv
    cli_headful = "--show" in sys.argv
    try:
        asyncio.run(run(
            dry_run=True if cli_dry_run else None,
            headless=False if cli_headful else None,
        ))
    except KeyboardInterrupt:
        logger.info("\n...Bot manually interrupted. Exiting.")
