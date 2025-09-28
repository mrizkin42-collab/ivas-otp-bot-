#!/usr/bin/env python3
"""
main.py
Core application: starts Playwright (headless), logs into the virtual-number site,
monitors the messages/OTP page and forwards new OTPs to the configured Telegram chat.
"""

import os
import time
import json
import re
import logging
import signal
import sys
from datetime import datetime
from typing import List, Dict, Optional

import telebot
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from config import settings

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("otp_monitor")

# --- Notifier ---
class Notifier:
    def __init__(self, token: str, chat_id: int):
        self.chat_id = chat_id
        self.bot = telebot.TeleBot(token, threaded=False)

    def send(self, text: str):
        try:
            self.bot.send_message(self.chat_id, text)
            logger.info("Sent Telegram message.")
        except Exception as e:
            logger.exception("Failed to send Telegram message: %s", e)

# --- Utils for last-seen persistence ---
LAST_SEEN_FILE = os.getenv("LAST_SEEN_FILE", "last_seen.json")


def load_last_seen() -> Optional[str]:
    try:
        if os.path.exists(LAST_SEEN_FILE):
            with open(LAST_SEEN_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("last_id")
    except Exception:
        logger.exception("Failed to read last seen file.")
    return None


def save_last_seen(last_id: str):
    try:
        with open(LAST_SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump({"last_id": last_id}, f)
        logger.info("Updated last seen id: %s", last_id)
    except Exception:
        logger.exception("Failed to save last seen id.")


# --- OTP extractor ---
OTP_REGEX = re.compile(r"\b(\d{4,8})\b")  # adjust range if site uses different length


def extract_otp(text: str) -> Optional[str]:
    if not text:
        return None
    m = OTP_REGEX.search(text)
    return m.group(1) if m else None


# --- Browser monitor (Playwright wrapper) ---
class BrowserMonitor:
    def __init__(self, notifier: Notifier):
        self.notifier = notifier
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

        # Selectors (can be overridden by environment variables set in .env)
        self.username_selector = settings.USERNAME_INPUT_SELECTOR
        self.password_selector = settings.PASSWORD_INPUT_SELECTOR
        self.submit_selector = settings.SUBMIT_BUTTON_SELECTOR
        self.messages_container_selector = settings.MESSAGES_CONTAINER_SELECTOR
        self.message_item_selector = settings.MESSAGE_ITEM_SELECTOR
        self.message_id_attr = settings.MESSAGE_ID_ATTR
        self.number_selector = settings.NUMBER_SELECTOR
        self.service_selector = settings.SERVICE_SELECTOR
        self.message_text_selector = settings.MESSAGE_TEXT_SELECTOR
        self.timestamp_selector = settings.TIMESTAMP_SELECTOR

    def start(self):
        logger.info("Starting Playwright browser (headless).")
        self.playwright = sync_playwright().start()
        # Add '--no-sandbox' for container platforms if needed
        self.browser = self.playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        self.context = self.browser.new_context()
        self.page = self.context.new_page()

    def stop(self):
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            logger.info("Playwright stopped gracefully.")
        except Exception:
            logger.exception("Error while stopping Playwright.")

    def login(self) -> bool:
        """
        Log in to the website.
        Uses WEBSITE_URL, WEBSITE_USERNAME, WEBSITE_PASSWORD from settings.
        Returns True when login succeeds (detected by OTP_PAGE_URL or messages container).
        """
        try:
            logger.info("Navigating to login page: %s", settings.WEBSITE_URL)
            self.page.goto(settings.WEBSITE_URL, timeout=30000)
            time.sleep(1)

            # The following selectors are placeholders. Update them!
            logger.info("Filling username/password with selectors: %s, %s", self.username_selector, self.password_selector)
            if self.username_selector:
                self.page.fill(self.username_selector, settings.WEBSITE_USERNAME)
            else:
                logger.warning("USERNAME_INPUT_SELECTOR is empty; update it in environment or config.")

            if self.password_selector:
                self.page.fill(self.password_selector, settings.WEBSITE_PASSWORD)
            else:
                logger.warning("PASSWORD_INPUT_SELECTOR is empty; update it in environment or config.")

            # Click login/submit
            if self.submit_selector:
                self.page.click(self.submit_selector)
            else:
                logger.warning("SUBMIT_BUTTON_SELECTOR is empty; update it in environment or config.")
            # Wait for either OTP_PAGE_URL or messages container to appear
            if settings.OTP_PAGE_URL:
                try:
                    # Wait up to 15s for navigation to OTP page
                    logger.info("Waiting for OTP page URL: %s", settings.OTP_PAGE_URL)
                    self.page.wait_for_url(settings.OTP_PAGE_URL, timeout=15000)
                    logger.info("Detected OTP page URL.")
                    return True
                except PlaywrightTimeoutError:
                    logger.warning("Timeout waiting for OTP_PAGE_URL.")
            # fallback: wait for messages container
            if self.messages_container_selector:
                try:
                    self.page.wait_for_selector(self.messages_container_selector, timeout=15000)
                    logger.info("Messages container detected after login.")
                    return True
                except PlaywrightTimeoutError:
                    logger.warning("Timeout waiting for messages container.")
            # If neither detection succeeded, try a quick URL check
            current_url = self.page.url
            logger.info("Current page after login attempt: %s", current_url)
            if settings.OTP_PAGE_URL and settings.OTP_PAGE_URL in current_url:
                return True

            return False
        except Exception as e:
            logger.exception("Login error: %s", e)
            return False

    def fetch_messages(self) -> List[Dict]:
        """
        Scrape messages/OTPs from the OTP page and return a list of message dicts:
        [{'id': ..., 'number':..., 'service':..., 'text':..., 'time':..., 'otp':...}, ...]
        The function does best-effort extraction using configured selectors.
        """
        messages = []
        try:
            # Navigate or refresh OTP page
            if settings.OTP_PAGE_URL:
                self.page.goto(settings.OTP_PAGE_URL, timeout=15000)
            else:
                # refresh current page
                self.page.reload()

            # Optionally wait for container
            if self.messages_container_selector:
                try:
                    self.page.wait_for_selector(self.messages_container_selector, timeout=5000)
                except PlaywrightTimeoutError:
                    # Continue, element might still be there
                    pass

            elements = self.page.query_selector_all(self.message_item_selector)
            logger.info("Found %d message elements.", len(elements))

            for el in elements:
                try:
                    raw_text = ""
                    msg_id = None

                    if self.message_id_attr:
                        msg_id = el.get_attribute(self.message_id_attr)

                    # If no id attr, create a synthetic id (hash of text)
                    if not msg_id:
                        raw_text = el.text_content() or ""
                        msg_id = str(abs(hash(raw_text)))[:32]

                    # number
                    number = "N/A"
                    if self.number_selector:
                        number_el = el.query_selector(self.number_selector)
                        number = (number_el.text_content().strip() if number_el else "N/A")

                    # service/platform
                    service = "N/A"
                    if self.service_selector:
                        s_el = el.query_selector(self.service_selector)
                        service = (s_el.text_content().strip() if s_el else "N/A")

                    # message text
                    if self.message_text_selector:
                        t_el = el.query_selector(self.message_text_selector)
                        text = (t_el.text_content().strip() if t_el else (raw_text or (el.text_content() or "")))
                    else:
                        text = raw_text or (el.text_content() or "")

                    # timestamp
                    timestamp = ""
                    if self.timestamp_selector:
                        tt_el = el.query_selector(self.timestamp_selector)
                        timestamp = (tt_el.text_content().strip() if tt_el else "")

                    otp = extract_otp(text)

                    messages.append({
                        "id": msg_id,
                        "number": number,
                        "service": service,
                        "text": text,
                        "time": timestamp,
                        "otp": otp
                    })
                except Exception:
                    logger.exception("Error parsing a message element; skipping it.")
                    continue

            # Assume elements are ordered newest-first (adjust in README if different)
            return messages
        except Exception:
            logger.exception("fetch_messages failed.")
            return []


# --- Application main loop and graceful shutdown ---
running = True


def signal_handler(sig, frame):
    global running
    running = False
    logger.info("Received termination signal. Shutting down...")
    try:
        notifier.send("🔌 Bot is shutting down gracefully.")
    except Exception:
        pass
    # Playwright cleanup will happen in main loop
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# notifier will be created later (global for signal handler)
notifier = None


def main():
    global notifier
    notifier = Notifier(settings.TELEGRAM_BOT_TOKEN, settings.TELEGRAM_CHAT_ID)

    # Send startup status
    notifier.send("✅ Bot Started Successfully. Initializing configuration and web automation environment.")

    # Outer loop attempts to keep the bot running and restart on critical errors
    while running:
        monitor = BrowserMonitor(notifier)
        try:
            monitor.start()
            time.sleep(1)
            # Attempt login
            login_ok = monitor.login()
            if login_ok:
                notifier.send("🌐 Login Successful! Session established. Starting continuous OTP monitoring loop.")
            else:
                notifier.send("❌ Login Failed! Please check WEBSITE_USERNAME and WEBSITE_PASSWORD. Retrying in 60 seconds.")
                monitor.stop()
                time.sleep(60)
                continue

            last_seen = load_last_seen()
            # On first run (no last_seen), do initial sync: set last_seen to latest message to avoid sending large backlog.
            first_run = (last_seen is None)

            while running:
                try:
                    messages = monitor.fetch_messages()
                    if not messages:
                        logger.debug("No messages found.")
                    else:
                        # messages assumed newest-first
                        ids = [m["id"] for m in messages]
                        if first_run:
                            # set last_seen to latest message and do not notify old messages
                            last_seen = ids[0]
                            save_last_seen(last_seen)
                            first_run = False
                            logger.info("Initial sync done. last_seen set to %s", last_seen)
                        else:
                            new_msgs = []
                            if last_seen in ids:
                                idx = ids.index(last_seen)
                                new_msgs = messages[:idx]  # messages newer than last_seen
                            else:
                                # last_seen not found (maybe rotated) — treat all as new but limit to recent N (safety)
                                new_msgs = messages[:10]

                            if new_msgs:
                                # Send notifications oldest -> newest so they appear in chronological order
                                for msg in reversed(new_msgs):
                                    if msg.get("otp"):
                                        ts = msg.get("time") or datetime.utcnow().isoformat()
                                        text = (
                                            "⭐ NEW OTP RECEIVED! ⭐\n"
                                            "-------------------------------------\n"
                                            f"🔢 Virtual Number: {msg.get('number')}\n"
                                            f"📦 Service: {msg.get('service')}\n"
                                            f"🔑 OTP Code: `{msg.get('otp')}`\n"
                                            f"⏰ Time: {ts}\n"
                                            "-------------------------------------"
                                        )
                                    else:
                                        # message without clear otp - still notify (optional)
                                        ts = msg.get("time") or datetime.utcnow().isoformat()
                                        text = (
                                            "⭐ NEW MESSAGE (no OTP detected) ⭐\n"
                                            "-------------------------------------\n"
                                            f"🔢 Virtual Number: {msg.get('number')}\n"
                                            f"📦 Service: {msg.get('service')}\n"
                                            f"📩 Message: {msg.get('text')[:400]}\n"
                                            f"⏰ Time: {ts}\n"
                                            "-------------------------------------"
                                        )
                                    notifier.send(text)
                                # update last_seen to the newest of the new messages
                                last_seen = new_msgs[0]["id"]
                                save_last_seen(last_seen)
                            else:
                                logger.debug("No new messages since last seen id: %s", last_seen)

                    time.sleep(settings.CHECK_INTERVAL)
                except PlaywrightTimeoutError:
                    logger.exception("Timeout during fetch loop; will retry shortly.")
                    notifier.send("⚠️ Warning: Timeout while fetching messages. Will retry.")
                    time.sleep(10)
                except Exception as e:
                    logger.exception("Critical error inside monitoring loop: %s", e)
                    notifier.send(f"⚠️ Critical Error Detected! The monitoring process stopped. Error: {str(e)}. Attempting graceful restart...")
                    # break to outer loop to restart browser and login again
                    break
        except Exception as e:
            logger.exception("Unexpected error in outer loop: %s", e)
            notifier.send(f"⚠️ Critical Error Detected! Error: {str(e)}. Retrying in 30 seconds...")
            time.sleep(30)
        finally:
            try:
                monitor.stop()
            except Exception:
                pass
            # Wait a short time before restart to avoid rapid loops
            time.sleep(5)

    # cleanup
    try:
        monitor.stop()
    except Exception:
        pass
    notifier.send("🔌 Bot stopped.")

if __name__ == "__main__":
    main()
