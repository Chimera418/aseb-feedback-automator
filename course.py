#!/usr/bin/env python3

"""
MyAmrita Student Portal Course Feedback Automation Script

This script automates the "Course Feedback" process from end-to-end.
The workflow for Course Feedback is slightly different from TLP Feedback:
1. Navigate to course-feedback-list
2. Send & Verify OTP FIRST
3. Fill out the feedback forms
4. Click Finish and handle JS Alert confirmation
"""

import asyncio
import re
import os
import getpass
from playwright.async_api import async_playwright, Page, BrowserContext, Locator
import time
import builtins
import logging

os.makedirs("logs", exist_ok=True)
os.makedirs("images", exist_ok=True)

# --- Setup Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/course_feedback_bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# --- Configuration (Can be overridden by environment variables) ---

ANSWER_OPTION_INDEX = int(os.environ.get("ANSWER_OPTION_INDEX", 1))
OUTLOOK_EMAIL = os.environ.get("OUTLOOK_EMAIL", "bl.sc.u4aie24103@bl.students.amrita.edu")
HEADLESS = os.environ.get("HEADLESS", "true").lower() in ["true", "1"]

# Portal URLs
DASHBOARD_URL = "https://students.amrita.edu/client/index"
FEEDBACK_URL = "https://students.amrita.edu/client/course-feedback-list"
OUTLOOK_URL = "https://outlook.office.com/mail/inbox"
PORTAL_BASE_URL = "https://students.amrita.edu/client/"

# --- Robust Selectors (as defined by requirements) ---
SEL = {
    "login_email": "input[name='loginfmt']",
    "login_next": "#idSIButton9",
    "portal_initial_login_span": "span.font-lg:has-text('LOGIN')",
    "login_work_school": "div[data-bind*='EstsAccountType_WorkSchool']",
    "login_password": "input[name='passwd']",
    "login_no_stay": "#idBtn_Back, button:has-text('No')",
    "portal_login_indicator": "a:has-text('FEEDBACK')",  # Broadened to match any feedback
    "portal_table": "table#home_tab",
    "portal_rows_to_check": "tr:has(a:has-text('Submit Feedback'))",
    "portal_row_status_cell": "th:last-child",
    "portal_row_link": "a:has-text('Submit Feedback')",
    "outlook_inbox": "div[role='listbox']",
    "outlook_email_body": "div[aria-label*='Message body'], div.BodyFragment, div[role='document']",
    "form_active_step": "div.step-content:visible, div.step-item.active, div.step-item.show, div.step-item.current",
    "form_answer_label": "label.form-check-label",
    "form_answer_radio": "input[type='radio']",
    "form_next_btn": "button[name='submit_ans']:not(:has-text('Back')), .next-btn:not(:has-text('Back')), button:has-text('Next'), button:has-text('Save & Next')",
    "form_remarks_box": "textarea",
    "form_remarks_save": "button:has-text('Save'), button:has-text('Submit')",
    "form_finish_btn": "button[name='finish_feedback'], button:has-text('Finish')",
    "form_finish_fallback": "button:has-text('Proceed'), button:has-text('Continue'), button:has-text('Next'), button:has-text('Submit')",
    "form_otp_send": "button:has-text('SEND OTP'), button:has-text('Send OTP')",
    "form_otp_input": "input[placeholder*='OTP' i], input[name*='otp' i]",
    "form_otp_validate": "button:has-text('Validate'), button:has-text('Submit'), button:has-text('Verify'), button[name='otp_ver']"
}

# --- Helper: Microsoft Login ---
async def login_to_microsoft(page: Page, email: str, password: str) -> None:
    try:
        logger.info("...Waiting for Microsoft login page to load.")
        await page.wait_for_selector(SEL["login_email"], timeout=20000)
        logger.info("...Entering email.")
        await page.fill(SEL["login_email"], email)
        await page.click(SEL["login_next"], timeout=15000)
        try:
            logger.info("...Checking for 'Work/School' account prompt.")
            await page.locator(SEL["login_work_school"]).click(timeout=5000)
            logger.info("...Selected 'Work or school account'.")
        except Exception:
            logger.info("... 'Work/School' prompt not found, proceeding to password.")
        logger.info("...Entering password.")
        await page.wait_for_selector(SEL["login_password"], timeout=15000)
        await page.fill(SEL["login_password"], password)
        await page.click(SEL["login_next"], timeout=15000)
        try:
            logger.info("...Handling 'Stay signed in?' prompt.")
            await page.locator(SEL["login_no_stay"]).first.click(timeout=15000)
            logger.info("...Clicked 'No' successfully.")
        except Exception:
            logger.info("... 'Stay signed in' prompt not found, proceeding.")
    except Exception as e:
        logger.info(f"❌ Error during Microsoft login: {e}")
        await page.screenshot(path="images/course_login_error.png")
        raise

# --- Helper: Outlook OTP Fetch ---
async def fetch_otp_from_outlook(context: BrowserContext, email: str, password: str) -> str:
    MAX_OTP_ATTEMPTS = 3
    for attempt in range(1, MAX_OTP_ATTEMPTS + 1):
        logger.info(f"...Attempting to fetch OTP (Attempt {attempt}/{MAX_OTP_ATTEMPTS})...")
        outlook_page = None
        try:
            outlook_page = await context.new_page()
            await outlook_page.goto(OUTLOOK_URL, timeout=120000)
            inbox_selector = SEL["outlook_inbox"]

            try:
                await outlook_page.wait_for_selector(SEL["login_email"], timeout=15000)
                logger.info("...Not logged in. Attempting Outlook login...")
                await login_to_microsoft(outlook_page, email, password)
            except Exception:
                logger.info("...Already logged in to Outlook.")

            await outlook_page.wait_for_selector(inbox_selector, timeout=60000)
            logger.info("...Outlook inbox loaded. Looking for newest OTP email.")

            otp_email_row = outlook_page.locator(f"text='OTP for Student Portal Feedback'").first
            await otp_email_row.click(timeout=10000)

            email_body_selector = SEL["outlook_email_body"]
            await outlook_page.wait_for_selector(email_body_selector, timeout=30000)
            email_bodies = await outlook_page.locator(email_body_selector).all_inner_texts()
            email_body = "\n".join(email_bodies)

            otp = None
            matches = re.findall(r"(?:is|otp)[\s:]*([A-Za-z0-9]{4,8})\b", email_body, re.IGNORECASE)
            if not matches:
                matches = re.findall(r"\b(\d{6})\b", email_body)
            if not matches:
                matches = re.findall(r"\b([A-Z0-9]{6})\b", email_body)

            if matches:
                otp = matches[-1]
            else:
                all_codes = re.findall(r"\b([A-Za-z0-9]{4,8})\b", email_body)
                if not all_codes:
                    logger.info(f"DEBUG: Email body text: {email_body[:500]}...")
                    raise RuntimeError("OTP not found in email body.")
                filtered_codes = [c for c in all_codes if not c.isalpha() or c.isupper()]
                if filtered_codes:
                    otp = filtered_codes[-1]
                else:
                    otp = all_codes[-1]

            logger.info(f"✅ OTP Extracted: {otp}\n")
            await outlook_page.close()
            return otp

        except Exception as e:
            logger.info(f"❌ Error during OTP fetch (Attempt {attempt}): {e}")
            if outlook_page:
                await outlook_page.screenshot(path="images/course_outlook_error.png")
                await outlook_page.close()
            if attempt < MAX_OTP_ATTEMPTS:
                logger.info("...Retrying in 5 seconds.")
                await asyncio.sleep(5)
            else:
                raise RuntimeError("Failed to fetch OTP after all attempts.")
    raise RuntimeError("Failed to fetch OTP.")

# --- Core Logic: Handle OTP First ---
async def verify_otp(page: Page, context: BrowserContext, email: str, password: str) -> None:
    logger.info("🔑 Checking if OTP verification is required...")
    try:
        otp_send_btn = page.locator(SEL["form_otp_send"])
        
        needs_otp = False
        try:
            await otp_send_btn.wait_for(state="visible", timeout=5000)
            needs_otp = True
        except Exception:
            pass
            
        if needs_otp:
            logger.info("...OTP Page detected. Clicking 'SEND OTP'.")
            await otp_send_btn.click(timeout=5000, no_wait_after=True)
            logger.info("...Waiting 8 seconds for OTP email to arrive...")
            await page.wait_for_timeout(8000)

            otp = await fetch_otp_from_outlook(context, email, password)

            await page.fill(SEL["form_otp_input"], otp)
            logger.info("...OTP filled. Clicking 'Validate'.")

            await page.locator(SEL["form_otp_validate"]).click(timeout=8000, no_wait_after=True)

            try:
                await page.locator(SEL["form_otp_input"]).wait_for(state="hidden", timeout=12000)
                logger.info("✅ OTP Validation Successful.\n")
            except Exception:
                logger.info("⚠️ OTP Validation failed! The OTP might be incorrect, or the portal rejected it.")
                raise RuntimeError("OTP Validation failed. Incorrect OTP?")
        else:
            logger.info("✅ OTP bypassed or already verified. Proceeding to feedback form.")
            
    except Exception as e:
        logger.info(f"❌ Error during OTP verification: {e}")
        await page.screenshot(path="images/course_otp_error.png")
        raise

# --- Core Logic: Fill Feedback ---
async def fill_feedback(page: Page, answer_idx: int) -> None:
    logger.info("📝 Starting to fill feedback form...")
    question_count = 1

    while True:
        logger.info(f"...Processing Question {question_count}")

        active_step = None
        try:
            active_step = page.locator(SEL["form_active_step"]).first
            await active_step.wait_for(state="visible", timeout=15000)
        except Exception:
            if await page.locator(f"{SEL['form_finish_btn']}").count() > 0:
                logger.info("...Could not find active step, but end-of-form detected. Proceeding.")
                break
            raise RuntimeError("Could not find active step and not at end of form.")

        try:
            answer_label = active_step.locator(SEL["form_answer_label"]).nth(answer_idx)
            await answer_label.hover(timeout=2000)
            await page.wait_for_timeout(50)
            await answer_label.click(timeout=3000)
            logger.info(f"...Selected answer {answer_idx} (via label).")
        except Exception:
            logger.info(f"...Label click failed. Retrying with force-check on radio button.")
            answer_radio = active_step.locator(SEL["form_answer_radio"]).nth(answer_idx)
            await answer_radio.check(force=True, timeout=3000)
            logger.info(f"...Selected answer {answer_idx} (via radio force-check).")

        await page.wait_for_timeout(300)

        next_button = active_step.locator(SEL["form_next_btn"]).locator("visible=true").first
        if not await next_button.count():
            # Check for Finish button since we can't find Save & Next
            finish_btn = page.locator(SEL["form_finish_btn"]).locator("visible=true").first
            if await finish_btn.count() > 0:
                logger.info(f"...Reached 'Finish' button after {question_count-1} questions.")
                break
            
            logger.info("⚠️ No visible 'Save' or 'Next' button found. Breaking loop.")
            break

        try:
            current_question_html = await active_step.inner_html()
        except Exception:
            current_question_html = ""

        MAX_CLICK_ATTEMPTS = 3
        POLL_TIMEOUT_SECONDS = 60
        advanced_to_next_question = False

        for attempt in range(MAX_CLICK_ATTEMPTS):
            logger.info(f"...Clicking 'Next' (Attempt {attempt + 1}/{MAX_CLICK_ATTEMPTS})")
            current_url = page.url
            try:
                await next_button.click(no_wait_after=True, timeout=5000)
            except Exception as e:
                logger.info(f"...Click itself failed: {e}. Retrying poll anyway.")

            start_time = time.time()
            dom_changed = False
            while time.time() - start_time < POLL_TIMEOUT_SECONDS:

                # Check if the page has fully navigated (window.location.href style)
                if page.url != current_url:
                    logger.info(f"...Page navigated to: {page.url}")
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=15000)
                    except Exception:
                        pass
                    dom_changed = True
                    break

                try:
                    current_active_step = page.locator(SEL["form_active_step"]).first
                    if not await current_active_step.is_visible(timeout=100):
                        dom_changed = True
                        break
                    new_html = await current_active_step.inner_html()
                    if new_html != current_question_html:
                        dom_changed = True
                        break
                except Exception:
                    dom_changed = True
                    break

                if await page.locator(f"{SEL['form_finish_btn']}").count() > 0:
                    logger.info("...Landed on finish page (detected during poll).")
                    advanced_to_next_question = True
                    break

                await page.wait_for_timeout(250)

            if advanced_to_next_question:
                break

            if dom_changed:
                logger.info("...DOM change detected. Waiting for new question to be stable.")
                try:
                    new_active_step = page.locator(SEL["form_active_step"]).first
                    await new_active_step.wait_for(state="visible", timeout=10000)
                    await new_active_step.locator(SEL["form_answer_label"]).first.wait_for(state="visible", timeout=10000)
                    logger.info("...New question is stable.")
                    advanced_to_next_question = True
                    break
                except Exception as e:
                    logger.info(f"...DOM changed but new question is not stable: {e}. Retrying click.")
            else:
                logger.info(f"...{POLL_TIMEOUT_SECONDS}s timeout reached, DOM did not change.")

        if not advanced_to_next_question:
            if await page.locator(f"{SEL['form_finish_btn']}").count() > 0:
                logger.info("...Landed on finish page (detected after all attempts).")
                break
            else:
                raise RuntimeError(f"Failed to advance to next question after {MAX_CLICK_ATTEMPTS} click attempts.")

        question_count += 1
        await page.wait_for_timeout(250)

# --- Core Logic: Finish with JS Alert ---
async def verify_finish(page: Page) -> None:
    logger.info("🔚 Starting final verification...")
    try:
        if await page.locator(SEL["form_remarks_box"]).count() > 0:
            logger.info("...Remarks page found. Skipping...")
            try:
                save_btn = page.locator(SEL["form_remarks_save"]).first
                if await save_btn.count() > 0:
                    await save_btn.click(timeout=3000, no_wait_after=True)
            except Exception:
                logger.info("...No save button on remarks page, proceeding.")

        # Setup dialog handler BEFORE clicking finish
        # The user mentioned a "confirmation alert popup comes which is the javascript alert box kinda thing"
        async def handle_dialog(dialog):
            logger.info(f"...Dialog popped up: {dialog.message}. Accepting it.")
            await dialog.accept()
        
        page.on("dialog", handle_dialog)

        finish_btn = page.locator(SEL["form_finish_btn"])
        if await finish_btn.count() > 0:
            logger.info("...Clicking 'Finish' button.")
            await finish_btn.click(timeout=3000, no_wait_after=True)
            await page.wait_for_timeout(2000)
            logger.info("✅ Course Feedback Submitted Successfully.\n")
            return

        for text in ["Proceed", "Continue", "Next", "Submit", "Finish", "FINISH"]:
            fallback_btn = page.locator(f"button:has-text('{text}'), a:has-text('{text}'), .step-item:has-text('{text}')").locator("visible=true").first
            if await fallback_btn.count() > 0:
                logger.info(f"...Clicking fallback button/step: '{text}'.")
                await fallback_btn.click(timeout=2000, no_wait_after=True)
                await page.wait_for_timeout(2000)
                logger.info("✅ Course Feedback Submitted Successfully.\n")
                break

    except Exception as e:
        logger.info(f"❌ Error during final verification: {e}")
        await page.screenshot(path="images/course_verify_error.png")
        raise

# --- Main Orchestrator ---
async def run(email=None, password=None, answer_idx=None, headless=None, progress_callback=None, user_config_queue=None) -> None:
    final_email = email if email is not None else OUTLOOK_EMAIL
    final_answer_idx = answer_idx if answer_idx is not None else ANSWER_OPTION_INDEX
    final_headless = headless if headless is not None else HEADLESS

    logger.info("--- MyAmrita Course Feedback Bot ---")
    logger.info(f"Email: {final_email}")
    logger.info(f"Headless Mode: {final_headless}")
    logger.info(f"Answer Index: {final_answer_idx} (0=Excellent)")

    final_password = password
    if not final_password:
        try:
            final_password = getpass.getpass("Enter your password (used for MyAmrita and Outlook): ")
        except Exception as e:
            logger.info(f"❌ Could not read password: {e}")
            return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=final_headless)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            logger.info(f"🔗 Opening Student Portal Dashboard: {DASHBOARD_URL}")
            await page.goto(DASHBOARD_URL, timeout=120000)
            login_indicator = SEL["portal_login_indicator"]

            try:
                await page.wait_for_selector(login_indicator, timeout=10000)
                logger.info("✅ Already logged in to Student Portal.")
            except Exception:
                logger.info("...Not logged in. Checking for login page type.")
                initial_login_span = page.locator(SEL["portal_initial_login_span"])
                if await initial_login_span.count() > 0:
                    logger.info("...Initial portal login page found. Clicking LOGIN span.")
                    await initial_login_span.click(timeout=15000, no_wait_after=True)
                    logger.info("...LOGIN span clicked. Waiting for Microsoft login page...")
                else:
                    logger.info("...Initial portal login span not found. Assuming direct Microsoft login.")

                await login_to_microsoft(page, final_email, final_password)
                await page.wait_for_selector(login_indicator, timeout=60000)
                logger.info("✅ Student Portal login successful.")

            logger.info(f"🔗 Navigating to feedback list: {FEEDBACK_URL}")
            await page.goto(FEEDBACK_URL)
            await page.wait_for_selector(SEL["portal_table"])
            logger.info("...Feedback list page loaded.")

            pending_feedbacks = []
            all_rows = await page.locator(SEL["portal_rows_to_check"]).all()

            logger.info(f"...Found {len(all_rows)} total feedback rows. Checking status...")

            for row in all_rows:
                status_text = await row.locator(SEL["portal_row_status_cell"]).inner_text()
                if status_text.strip().lower() == "completed":
                    continue

                row_info = await row.evaluate("""(row) => {
                    let courseInfo = row.cells[1] ? row.cells[1].innerText.trim().replace(/\\n/g, ' - ') : 'Unknown Course';
                    let className = row.cells[2] ? row.cells[2].innerText.trim() : '';
                    return courseInfo + ' | ' + className;
                }""")
                
                row_info = row_info.replace('\r', '').replace('\n', ' ').strip()
                logger.info(f"...Found pending feedback (Status: '{status_text.strip()}')")
                href = await row.locator(SEL["portal_row_link"]).first.get_attribute("href")

                if href and (href.startswith("feedback?") or href.startswith("course-feedback?")):
                    pending_feedbacks.append({
                        "url": f"{PORTAL_BASE_URL}{href}",
                        "info": row_info
                    })
                elif href:
                    logger.info(f"⚠️ Found unknown href format, skipping: {href}")

            total_pending = len(pending_feedbacks)
            logger.info(f"\n📚 Pending Course Feedbacks Found: {total_pending}\n")
            
            if progress_callback:
                progress_callback("fetch_complete", pending_feedbacks)

            if total_pending == 0:
                logger.info("🎉 No pending feedbacks. You're all set!")
                await browser.close()
                return

            if user_config_queue:
                logger.info("⏳ Waiting for user to confirm ratings in GUI...")
                if progress_callback:
                    progress_callback("waiting_for_user", pending_feedbacks)
                
                while user_config_queue.empty():
                    await asyncio.sleep(0.5)
                
                user_config = user_config_queue.get()
                if user_config == "CANCEL":
                    logger.info("🚫 Automation cancelled by user.")
                    return
            else:
                user_config = {item["info"]: final_answer_idx for item in pending_feedbacks}

            for idx, item in enumerate(pending_feedbacks):
                subject_num = idx + 1
                href = item["url"]
                info = item["info"]
                logger.info(f"➡️ Processing subject {subject_num}/{total_pending}")
                logger.info(f"📘 Subject Details: {info}")
                logger.info(f"...Opening: {href}")
                
                if progress_callback:
                    progress_callback("subject_processing", info)
                
                feedback_page = await context.new_page()

                try:
                    await feedback_page.goto(href, timeout=60000, wait_until="domcontentloaded")

                    subject_idx = user_config.get(info, final_answer_idx)
                    
                    # Workflow specific to Course Feedback:
                    # 1. OTP
                    await verify_otp(feedback_page, context, final_email, final_password)
                    
                    # 2. Fill feedback
                    await fill_feedback(feedback_page, subject_idx)
                    
                    # 3. Finish (with alert handler)
                    await verify_finish(feedback_page)
                    
                    if progress_callback:
                        progress_callback("subject_done", info)

                except Exception as e:
                    logger.info(f"--- ⚠️ FAILED TO SUBMIT SUBJECT {subject_num} ({href}) ---")
                    logger.info(f"Error: {e}")
                    logger.info("This feedback will be skipped. Check error screenshots.")
                    await feedback_page.screenshot(path=f"images/course_failure_subject_{subject_num}.png")
                    
                    if progress_callback:
                        progress_callback("subject_failed", info)

                finally:
                    await feedback_page.close()
                    await page.wait_for_timeout(500)

            logger.info("\n🎉 ✅ ALL COURSE FEEDBACK DONE — GO TOUCH GRASS 🌿\n")

        except Exception as e:
            logger.info(f"--- ❌ A FATAL ERROR OCCURRED ---")
            logger.info(f"Error: {e}")
            await page.screenshot(path="images/course_fatal_error.png")

        finally:
            await browser.close()

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("\n...Bot manually interrupted. Exiting.")
