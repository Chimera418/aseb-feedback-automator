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


async def safe_goto(page: Page, url: str, timeout: int = 60000, max_retries: int = 3) -> None:
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"🔗 Navigating to {url} (Attempt {attempt}/{max_retries})")
            await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            return
        except Exception as e:
            logger.warning(f"⚠️ Navigation failed: {e}")
            if attempt == max_retries:
                raise RuntimeError(f"Failed to load {url} after {max_retries} attempts. Last error: {e}")
            await asyncio.sleep(5)


async def login(page: Page, username: str, password: str) -> None:
    logger.info("🔐 Logging in to AmritaVidya...")
    await safe_goto(page, LOGIN_URL)
    await page.wait_for_selector(SEL["login_user"], timeout=20000)

    await page.fill(SEL["login_user"], username)
    await page.fill(SEL["login_pass"], password)

    await page.locator(SEL["login_submit"]).first.click(timeout=15000)
    await page.wait_for_load_state("domcontentloaded", timeout=30000)

    body = await page.inner_text("body")
    if "invalid" in body.lower() or "incorrect" in body.lower() or await page.locator(SEL["login_pass"]).count() > 0:
        await page.screenshot(path="images/vidya_login_error.png")
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


async def fill_feedback(page: Page, answer_idx: int) -> None:
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

    logger.info(f"📝 Filling {len(groups)} questions with option index {answer_idx} (clamped per question).")
    for name, count in groups:
        idx = min(answer_idx, count - 1)
        radios = page.locator(f"input[type='radio'][name='{name}']") if name else page.locator(SEL["form_radio"])
        await radios.nth(idx).check(force=True, timeout=5000)


async def submit_feedback(page: Page, subject_num: int, dry_run: bool = False) -> None:
    if dry_run:
        shot = f"images/vidya_dryrun_subject_{subject_num}.png"
        await page.screenshot(path=shot, full_page=True)
        logger.info(f"🧪 DRY RUN — form filled but NOT submitted. Screenshot: {shot}")
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
    logger.info(f"Answer Index: {final_answer_idx} (0=best option)")
    if final_dry_run:
        logger.info("🧪 DRY RUN enabled — forms will be filled but never submitted.")

    if not final_password:
        final_password = getpass.getpass("Enter your AmritaVidya password: ")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=final_headless)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            await login(page, username, final_password)

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
                    await page.screenshot(path=f"images/vidya_failure_subject_{idx}.png")

                    if progress_callback:
                        progress_callback("subject_failed", info)

            logger.info("\n🎉 ✅ ALL AMRITAVIDYA FEEDBACK DONE — GO TOUCH GRASS 🌿\n")

        except Exception as e:
            logger.info("--- ❌ A FATAL ERROR OCCURRED ---")
            logger.info(f"Error: {e}")
            await page.screenshot(path="images/vidya_fatal_error.png")

        finally:
            await browser.close()


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
