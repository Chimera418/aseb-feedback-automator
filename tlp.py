#!/usr/bin/env python3

"""
MyAmrita Student Portal TLP Feedback Automation Script

This script automates the "Class TLP Feedback" process from end-to-end.
It is hardened against the portal's unstable DOM, slow loads, and
inconsistent navigation by using a DOM-mutation-based waiting strategy
instead of relying on URL changes.

It logs in, finds pending feedback, fills all questions, handles the
multi-step finish/OTP process (including fetching the OTP from Outlook),
and safely skips any subject that fails, continuing with the rest.

Run with:
    python3 tlp.py

Required:
    pip install playwright
    playwright install chromium
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
        logging.FileHandler("logs/feedback_bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# --- Configuration (Can be overridden by environment variables) ---

# 0=Excellent, 1=Very Good, 2=Good, 3=Satisfactory, 4=Poor
# Set to '0' to select the first (top) option for all questions.
ANSWER_OPTION_INDEX = int(os.environ.get("ANSWER_OPTION_INDEX", 1))

# Your Amrita student email (e.g., bl.sc.u4aie24XXX@bl.students.amrita.edu)
OUTLOOK_EMAIL = os.environ.get("OUTLOOK_EMAIL", "bl.sc.u4aie24103@bl.students.amrita.edu")

# Set to "true" or "1" to run in headless mode
HEADLESS = os.environ.get("HEADLESS", "true").lower() in ["true", "1"]

# Portal URLs
DASHBOARD_URL = "https://students.amrita.edu/client/index"
FEEDBACK_URL = "https://students.amrita.edu/client/class-feedback"
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
    "portal_login_indicator": "a:has-text('TLP FEEDBACK')",
    "portal_table": "table#home_tab",
    "portal_rows_to_check": "tr:has(a:has-text('Submit Feedback'))",
    "portal_row_status_cell": "th:last-child",
    "portal_row_link": "a:has-text('Submit Feedback')",
    "outlook_inbox": "div[role='listbox']",
    "outlook_email_row": "span:has-text('OTP for Student Portal Feedback'), div:has-text('OTP for Student Portal Feedback')",
    "outlook_email_body": "div[aria-label*='Message body'], div.BodyFragment, div[role='document']",
    "form_active_step": "div.step-content:visible, div.step-item.active, div.step-item.show, div.step-item.current",
    "form_answer_label": "label.form-check-label",
    "form_answer_radio": "input[type='radio']",
    "form_next_btn": "button[name='submit_ans']:not(:has-text('Back')), .next-btn:not(:has-text('Back')), button:has-text('Next'), button:has-text('Save & Next')",
    "form_remarks_box": "textarea",
    "form_remarks_save": "button:has-text('Save'), button:has-text('Submit')",
    "form_finish_btn": "button[name='finish_feedback']",
    "form_finish_fallback": "button:has-text('Proceed'), button:has-text('Continue'), button:has-text('Next'), button:has-text('Submit')",
    "form_otp_send": "button:has-text('SEND OTP'), button:has-text('Send OTP')",
    "form_otp_input": "input[placeholder*='OTP' i], input[name*='otp' i]",
    "form_otp_validate": "button:has-text('Validate')"
}

# --- Helper: Safe Goto with Retries for 504/Timeouts ---
async def safe_goto(page: Page, url: str, timeout: int = 120000, wait_until: str = "load", max_retries: int = 3) -> None:
    """Navigates to a URL with built-in retries for 504 Gateway Timeouts and network errors."""
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"🔗 Navigating to {url} (Attempt {attempt}/{max_retries})")
            response = await page.goto(url, timeout=timeout, wait_until=wait_until)
            
            # Check for Bad Gateway / Gateway Timeout HTTP status
            if response and response.status in [502, 503, 504]:
                logger.warning(f"⚠️ Server returned HTTP {response.status}. Retrying in 10 seconds...")
                await asyncio.sleep(10)
                continue
                
            # Check if the page content itself indicates a 504 (sometimes load balancers do this with 200 OK)
            try:
                page_text = await page.content()
                if "504 Gateway Time-out" in page_text or "504 Gateway Timeout" in page_text or "502 Bad Gateway" in page_text:
                    logger.warning(f"⚠️ Page content indicates 504/502 error. Retrying in 10 seconds...")
                    await asyncio.sleep(10)
                    continue
            except Exception:
                pass
                
            # If we get here, it seems successful
            return
            
        except Exception as e:
            logger.warning(f"⚠️ Navigation failed: {e}. Retrying in 10 seconds...")
            if attempt == max_retries:
                raise RuntimeError(f"Failed to load {url} after {max_retries} attempts. Last error: {e}")
            await asyncio.sleep(10)

# --- Helper: Microsoft Login ---

async def login_to_microsoft(page: Page, email: str, password: str) -> None:
    """Reusable function to log in to a Microsoft account."""
    try:
        logger.info("...Waiting for Microsoft login page to load.")
        await page.wait_for_selector(SEL["login_email"], timeout=20000)

        # 1. Enter Email
        logger.info("...Entering email.")
        await page.fill(SEL["login_email"], email)
        await page.click(SEL["login_next"], timeout=15000)

        # 2. Handle "Work/School" prompt (if it appears)
        try:
            logger.info("...Checking for 'Work/School' account prompt.")
            await page.locator(SEL["login_work_school"]).click(timeout=5000)
            logger.info("...Selected 'Work or school account'.")
        except Exception:
            logger.info("... 'Work/School' prompt not found, proceeding to password.")

        # 3. Enter Password
        logger.info("...Entering password.")
        await page.wait_for_selector(SEL["login_password"], timeout=15000)
        await page.fill(SEL["login_password"], password)
        await page.click(SEL["login_next"], timeout=15000)

        # 4. Handle "Stay signed in?" prompt (click "No")
        try:
            logger.info("...Handling 'Stay signed in?' prompt.")
            await page.locator(SEL["login_no_stay"]).first.click(timeout=15000)
            logger.info("...Clicked 'No' successfully.")
        except Exception:
            logger.info("... 'Stay signed in' prompt not found, proceeding.")

    except Exception as e:
        logger.info(f"❌ Error during Microsoft login: {e}")
        await page.screenshot(path="images/login_error.png")
        raise

# --- Helper: Outlook OTP Fetch ---

async def fetch_otp_from_outlook(context: BrowserContext, email: str, password: str) -> str:
    """
    Opens Outlook in a new page, logs in if necessary, finds the newest
    OTP email, and extracts the code. Retries on failure.
    """
    MAX_OTP_ATTEMPTS = 3
    for attempt in range(1, MAX_OTP_ATTEMPTS + 1):
        logger.info(f"...Attempting to fetch OTP (Attempt {attempt}/{MAX_OTP_ATTEMPTS})...")
        outlook_page = None
        try:
            outlook_page = await context.new_page()
            await safe_goto(outlook_page, OUTLOOK_URL, timeout=120000)
            inbox_selector = SEL["outlook_inbox"]

            # 1. Login to Outlook if needed
            try:
                # Check if login form is present
                await outlook_page.wait_for_selector(SEL["login_email"], timeout=15000)
                logger.info("...Not logged in. Attempting Outlook login...")
                await login_to_microsoft(outlook_page, email, password)
            except Exception:
                logger.info("...Already logged in to Outlook.")

            # 2. Wait for inbox and find email
            await outlook_page.wait_for_selector(inbox_selector, timeout=60000)
            logger.info("...Outlook inbox loaded. Looking for newest OTP email.")

            # Click the *first* (newest) matching email row
            # Using a more generic text locator for better resilience
            otp_email_row = outlook_page.locator(f"text='OTP for Student Portal Feedback'").first
            await otp_email_row.click(timeout=10000)

            # 3. Extract OTP from email body
            email_body_selector = SEL["outlook_email_body"]
            await outlook_page.wait_for_selector(email_body_selector, timeout=30000)
            # Fetch all matching bodies (in case of a conversation thread) and join them
            email_bodies = await outlook_page.locator(email_body_selector).all_inner_texts()
            email_body = "\n".join(email_bodies)

            # Improved regex to find the OTP
            otp = None
            
            # 1. Look for explicit patterns like "is: 123456" or "OTP: 123456"
            matches = re.findall(r"(?:is|otp)[\s:]*([A-Za-z0-9]{4,8})\b", email_body, re.IGNORECASE)
            
            # 2. If not found, look for exactly 6 digits
            if not matches:
                matches = re.findall(r"\b(\d{6})\b", email_body)
                
            # 3. If not found, look for 6-character alphanumeric uppercase
            if not matches:
                matches = re.findall(r"\b([A-Z0-9]{6})\b", email_body)

            if matches:
                # Take the very last match found in the entire email thread
                otp = matches[-1]
            else:
                # Fallback to the original logic
                all_codes = re.findall(r"\b([A-Za-z0-9]{4,8})\b", email_body)
                if not all_codes:
                    logger.info(f"DEBUG: Email body text: {email_body[:500]}...")
                    raise RuntimeError("OTP not found in email body.")
                # We try to avoid taking common words
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
                await outlook_page.screenshot(path="images/outlook_error.png")
                await outlook_page.close()
            if attempt < MAX_OTP_ATTEMPTS:
                logger.info("...Retrying in 5 seconds.")
                await asyncio.sleep(5)
            else:
                raise RuntimeError("Failed to fetch OTP after all attempts.")

    raise RuntimeError("Failed to fetch OTP.") # Should be unreachable

# --- Core Logic: Fill Feedback ---

async def fill_feedback(page: Page, answer_idx: int) -> None:
    """
    Loops through the multi-step feedback form using a robust
    DOM-mutation-polling and retry-click strategy.
    """
    logger.info("📝 Starting to fill feedback form...")
    question_count = 1

    while True:
        logger.info(f"...Processing Question {question_count}")

        # 2. Find the active question container
        active_step = None
        try:
            active_step = page.locator(SEL["form_active_step"]).first
            await active_step.wait_for(state="visible", timeout=15000)
        except Exception:
            # This can happen if the previous click *did* work but
            # we failed to detect it. We check for end-of-form again.
            if await page.locator(f"{SEL['form_finish_btn']}, {SEL['form_otp_send']}").count() > 0:
                logger.info("...Could not find active step, but end-of-form detected. Proceeding.")
                break
            raise RuntimeError("Could not find active step and not at end of form.")

        # 3. Select the answer
        try:
            answer_label = active_step.locator(SEL["form_answer_label"]).nth(answer_idx)
            await answer_label.hover(timeout=2000)
            await page.wait_for_timeout(50) # Pause for JS
            await answer_label.click(timeout=3000)
            logger.info(f"...Selected answer {answer_idx} (via label).")
        except Exception:
            logger.info(f"...Label click failed. Retrying with force-check on radio button.")
            answer_radio = active_step.locator(SEL["form_answer_radio"]).nth(answer_idx)
            await answer_radio.check(force=True, timeout=3000)
            logger.info(f"...Selected answer {answer_idx} (via radio force-check).")

        await page.wait_for_timeout(300) # Pause for selection to register

        # 4. Find the 'Next' button (must be visible)
        next_button = active_step.locator(SEL["form_next_btn"]).locator("visible=true").first
        if not await next_button.count():
            # Check for Finish button since we can't find Save & Next
            finish_btn = page.locator(SEL["form_finish_btn"]).locator("visible=true").first
            if await finish_btn.count() > 0:
                logger.info(f"...Reached 'Finish' button after {question_count-1} questions.")
                break
                
            otp_btn = page.locator(SEL["form_otp_send"]).locator("visible=true").first
            if await otp_btn.count() > 0:
                logger.info(f"...Reached 'SEND OTP' button after {question_count-1} questions.")
                break
                
            logger.info("⚠️ No visible 'Save' or 'Next' button found. Breaking loop.")
            break

        # 5. Get a unique identifier for the *current* question
        # We use inner_html() as a snapshot of the current state.
        try:
            current_question_html = await active_step.inner_html()
        except Exception:
            # Element might have detached, this is fine, we'll just use a blank string
            current_question_html = ""

        # 6. Start the Poll-and-Retry-Click loop
        MAX_CLICK_ATTEMPTS = 3
        POLL_TIMEOUT_SECONDS = 60 # Give it 60s per click attempt
        advanced_to_next_question = False

        for attempt in range(MAX_CLICK_ATTEMPTS):
            logger.info(f"...Clicking 'Next' (Attempt {attempt + 1}/{MAX_CLICK_ATTEMPTS})")
            current_url = page.url
            try:
                # Fire the click, don't wait for navigation
                await next_button.click(no_wait_after=True, timeout=5000)
            except Exception as e:
                logger.info(f"...Click itself failed: {e}. Retrying poll anyway.")

            # 7. Poll for change — either page navigation OR DOM mutation
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
                    # Re-find the active step in case the old one is gone
                    current_active_step = page.locator(SEL["form_active_step"]).first

                    # Success if:
                    # 1. The step is no longer visible
                    if not await current_active_step.is_visible(timeout=100):
                        dom_changed = True
                        break

                    # 2. The step's content has changed
                    new_html = await current_active_step.inner_html()
                    if new_html != current_question_html:
                        dom_changed = True
                        break

                except Exception:
                    # 3. The element detached (also a success signal)
                    dom_changed = True
                    break

                # Also check for end-of-form as a success condition
                if await page.locator(f"{SEL['form_finish_btn']}, {SEL['form_otp_send']}").count() > 0:
                    logger.info("...Landed on finish/OTP page (detected during poll).")
                    advanced_to_next_question = True # Signal to exit outer loop
                    break

                await page.wait_for_timeout(250) # Poll every 250ms

            if advanced_to_next_question:
                break # Exit the 'for' loop (we're on the finish page)

            if dom_changed:
                logger.info("...DOM change detected. Waiting for new question to be stable.")
                # Wait for the *new* content to be stable
                try:
                    # Wait for a new active step to be visible
                    new_active_step = page.locator(SEL["form_active_step"]).first
                    await new_active_step.wait_for(state="visible", timeout=10000)
                    # And wait for its labels to appear
                    await new_active_step.locator(SEL["form_answer_label"]).first.wait_for(state="visible", timeout=10000)

                    logger.info("...New question is stable.")
                    advanced_to_next_question = True
                    break # Success! Exit the 'for' loop
                except Exception as e:
                    logger.info(f"...DOM changed but new question is not stable: {e}. Retrying click.")
            else:
                logger.info(f"...{POLL_TIMEOUT_SECONDS}s timeout reached, DOM did not change.")
                # Loop will continue to the next click attempt

        # 8. Check if all attempts failed
        if not advanced_to_next_question:
             # Check one last time if we're on the finish page
            if await page.locator(f"{SEL['form_finish_btn']}, {SEL['form_otp_send']}").count() > 0:
                logger.info("...Landed on finish/OTP page (detected after all attempts).")
                break # Exit the 'while' loop
            else:
                # All attempts failed, and we're not on the finish page.
                raise RuntimeError(f"Failed to advance to next question after {MAX_CLICK_ATTEMPTS} click attempts.")

        question_count += 1
        await page.wait_for_timeout(250) # Final small pause

# --- Core Logic: Finish & OTP Verification ---

async def verify_finish(page: Page, context: BrowserContext, email: str, password: str) -> None:
    """
    Handles the final "Remarks", "Finish", and OTP submission pages.
    """
    logger.info("🔚 Starting final verification...")

    try:
        # 1. Handle "Remarks" page (if it exists)
        if await page.locator(SEL["form_remarks_box"]).count() > 0:
            logger.info("...Remarks page found. Skipping...")
            try:
                save_btn = page.locator(SEL["form_remarks_save"]).first
                if await save_btn.count() > 0:
                    await save_btn.click(timeout=3000, no_wait_after=True)
            except Exception:
                logger.info("...No save button on remarks page, proceeding.")

        # 2. Handle "Finish" button
        finish_btn = page.locator(SEL["form_finish_btn"])
        if await finish_btn.count() > 0:
            logger.info("...Clicking 'Finish' button.")
            await finish_btn.click(timeout=3000, no_wait_after=True)
            await page.wait_for_timeout(1000) # Wait for next step to load

        # 3. Handle intermediate fallback buttons ("Proceed", "Continue", etc. or a "FINISH" wizard step)
        for text in ["Proceed", "Continue", "Next", "Submit", "Finish", "FINISH"]:
            fallback_btn = page.locator(f"button:has-text('{text}'), a:has-text('{text}'), .step-item:has-text('{text}')").locator("visible=true").first
            # Only click if it's not one of our main buttons
            if (await fallback_btn.count() > 0 and
                await page.locator(SEL["form_otp_send"]).count() == 0 and
                await page.locator(SEL["form_otp_validate"]).count() == 0):

                logger.info(f"...Clicking fallback button/step: '{text}'.")
                await fallback_btn.click(timeout=2000, no_wait_after=True)
                await page.wait_for_timeout(1000)
                break

        # 4. Handle OTP Page
        logger.info("...Waiting for OTP page to load.")
        otp_send_btn = page.locator(SEL["form_otp_send"])
        await otp_send_btn.wait_for(state="visible", timeout=20000)

        logger.info("...Clicking 'SEND OTP'.")
        await otp_send_btn.click(timeout=5000, no_wait_after=True)
        logger.info("...Waiting 8 seconds for OTP email to arrive...")
        await page.wait_for_timeout(8000) # Wait for OTP to be sent and arrive in inbox

        # Fetch OTP (with retries)
        otp = await fetch_otp_from_outlook(context, email, password)

        await page.fill(SEL["form_otp_input"], otp)
        logger.info("...OTP filled. Clicking 'Validate & Finish'.")

        await page.locator(SEL["form_otp_validate"]).click(timeout=8000, no_wait_after=True)

        # Wait for the submission to complete
        try:
            # If the OTP input disappears, submission was successful
            await page.locator(SEL["form_otp_input"]).wait_for(state="hidden", timeout=12000)
            logger.info("✅ Feedback Submitted Successfully.\n")
        except Exception:
            logger.info("⚠️ OTP Validation failed! The OTP might be incorrect, or the portal rejected it.")
            raise RuntimeError("OTP Validation failed. Incorrect OTP?")

    except Exception as e:
        logger.info(f"❌ Error during final verification: {e}")
        await page.screenshot(path="images/verify_error.png")
        raise

# --- Main Orchestrator ---

async def run(email=None, password=None, answer_idx=None, headless=None, progress_callback=None, user_config_queue=None) -> None:
    """
    Main function to launch the browser and orchestrate the entire
    feedback submission process.
    (UPDATED to handle initial portal login page)
    """
    final_email = email if email is not None else OUTLOOK_EMAIL
    final_answer_idx = answer_idx if answer_idx is not None else ANSWER_OPTION_INDEX
    final_headless = headless if headless is not None else HEADLESS

    logger.info("--- MyAmrita TLP Feedback Bot ---")
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
            # 1. Login to Student Portal
            logger.info(f"🔗 Opening Student Portal Dashboard: {DASHBOARD_URL}")
            await safe_goto(page, DASHBOARD_URL, timeout=120000)

            login_indicator = SEL["portal_login_indicator"]

            try:
                # --- THIS IS THE NEW, ROBUST LOGIN LOGIC ---

                # Check if we are ALREADY logged in
                await page.wait_for_selector(login_indicator, timeout=10000)
                logger.info("✅ Already logged in to Student Portal.")

            except Exception:
                # If not logged in, figure out WHICH login page we're on
                logger.info("...Not logged in. Checking for login page type.")

                # Check for the initial AUMS portal login span
                initial_login_span = page.locator(SEL["portal_initial_login_span"])

                if await initial_login_span.count() > 0:
                    # --- A: We are on the AUMS "pre-login" page ---
                    logger.info("...Initial portal login page found. Clicking LOGIN span.")
                    await initial_login_span.click(timeout=15000, no_wait_after=True)
                    logger.info("...LOGIN span clicked. Waiting for Microsoft login page...")
                else:
                    # --- B: We are (presumably) already on the Microsoft page ---
                    logger.info("...Initial portal login span not found. Assuming direct Microsoft login.")

                # Now, proceed with the standard Microsoft login flow
                await login_to_microsoft(page, final_email, final_password)

                # Wait for the dashboard to confirm successful login
                await page.wait_for_selector(login_indicator, timeout=60000)
                logger.info("✅ Student Portal login successful.")
                # --- END OF NEW LOGIN LOGIC ---

            # 2. Navigate to TLP Feedback list and find pending
            logger.info(f"🔗 Navigating to feedback list: {FEEDBACK_URL}")
            await safe_goto(page, FEEDBACK_URL)
            await page.wait_for_selector(SEL["portal_table"], timeout=30000)
            logger.info("...Feedback list page loaded.")

            pending_feedbacks = []
            all_rows = await page.locator(SEL["portal_rows_to_check"]).all()

            logger.info(f"...Found {len(all_rows)} total feedback rows. Checking status...")

            for row in all_rows:
                status_text = await row.locator(SEL["portal_row_status_cell"]).inner_text()

                if status_text.strip().lower() == "completed":
                    continue # Skip completed

                # Extract subject details properly from this weird rowspan table layout
                row_info = await row.evaluate("""(row) => {
                    let faculty = row.cells[0] ? row.cells[0].innerText.trim() : '';
                    let courseInfo = 'Unknown Course';
                    let current = row;
                    // Traverse backwards to find the header row containing the course info (it has rowspans)
                    while (current) {
                        if (current.querySelector('th[rowspan], td[rowspan]')) {
                            let headerCells = current.querySelectorAll('th, td');
                            if (headerCells.length >= 3) {
                                courseInfo = headerCells[2].innerText.trim().replace(/\\n/g, ' - ');
                            }
                            break;
                        }
                        current = current.previousElementSibling;
                    }
                    return courseInfo.replace(/[\\r\\n]+/g, ' ') + ' | ' + faculty.replace(/[\\r\\n]+/g, ' ');
                }""")
                
                # Double-check Python side to absolutely prevent log mangling
                row_info = row_info.replace('\r', '').replace('\n', ' ').strip()

                logger.info(f"...Found pending feedback (Status: '{status_text.strip()}')")
                href = await row.locator(SEL["portal_row_link"]).first.get_attribute("href")

                if href and href.startswith("feedback?"):
                    pending_feedbacks.append({
                        "url": f"{PORTAL_BASE_URL}{href}",
                        "info": row_info
                    })
                elif href:
                    logger.info(f"⚠️ Found unknown href format, skipping: {href}")

            total_pending = len(pending_feedbacks)
            logger.info(f"\n📚 Pending TLP Feedbacks Found: {total_pending}\n")
            
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

            # 3. Process each pending feedback in a new page
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
                    await safe_goto(feedback_page, href, timeout=60000, wait_until="domcontentloaded")

                    # Run the two-stage process
                    subject_idx = user_config.get(info, final_answer_idx)
                    await fill_feedback(feedback_page, subject_idx)
                    await verify_finish(feedback_page, context, final_email, final_password)
                    
                    if progress_callback:
                        progress_callback("subject_done", info)

                except Exception as e:
                    logger.info(f"--- ⚠️ FAILED TO SUBMIT SUBJECT {subject_num} ({href}) ---")
                    logger.info(f"Error: {e}")
                    logger.info("This feedback will be skipped. Check error screenshots.")
                    await feedback_page.screenshot(path=f"images/failure_subject_{subject_num}.png")
                    
                    if progress_callback:
                        progress_callback("subject_failed", info)

                finally:
                    await feedback_page.close()
                    await page.wait_for_timeout(500) # Brief pause

            logger.info("\n🎉 ✅ ALL TLP FEEDBACK DONE — GO TOUCH GRASS 🌿\n")

        except Exception as e:
            logger.info(f"--- ❌ A FATAL ERROR OCCURRED ---")
            logger.info(f"Error: {e}")
            await page.screenshot(path="images/fatal_error.png")

        finally:
            await browser.close()

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("\n...Bot manually interrupted. Exiting.")
