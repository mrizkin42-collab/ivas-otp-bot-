import os
import time
import logging
import signal
from datetime import datetime

from playwright.sync_api import sync_playwright, TimeoutError
import telebot
import config as settings  # uses constants from config.py


# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)


class TelegramNotifier:
    def __init__(self, token, chat_id):
        self.bot = telebot.TeleBot(token)
        self.chat_id = chat_id

    def send(self, message: str):
        try:
            self.bot.send_message(self.chat_id, message, parse_mode="Markdown")
            logging.info("Sent Telegram message.")
        except Exception as e:
            logging.error(f"Failed to send Telegram message: {e}")


class BrowserMonitor:
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier
        self.playwright = None
        self.browser = None
        self.page = None
        self.last_message_id = None
        self.running = True

    def start_browser(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True)
        self.page = self.browser.new_page()
        logging.info("Browser started.")

    def stop_browser(self):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        logging.info("Playwright stopped gracefully.")

    def login(self):
        try:
            self.page.goto(settings.WEBSITE_URL, timeout=60000)

            # ✅ Fill login form
            self.page.get_by_label("Email").fill(settings.WEBSITE_USERNAME)
            self.page.get_by_label("Password").fill(settings.WEBSITE_PASSWORD)
            self.page.get_by_role("button", name="Log in").click()

            # ✅ First try: wait for inbox element
            try:
                self.page.wait_for_selector("text=My SMS Statistics", timeout=30000)  # adjust text if needed
                logging.info("Inbox detected after login.")
            except TimeoutError:
                logging.warning("Inbox element not detected, navigating manually to OTP page...")
                self.page.goto(settings.OTP_PAGE_URL, timeout=60000)
                self.page.wait_for_selector("text=My SMS Statistics", timeout=30000)

            self.notifier.send("🌐 Login Successful! Session established. Starting continuous OTP monitoring loop.")
            logging.info("Login successful.")
            return True

        except Exception as e:
            self.notifier.send(f"❌ Login Failed! Error: {e}")
            logging.error(f"Login error: {e}")
            return False

    def check_new_messages(self):
        try:
            self.page.goto(settings.OTP_PAGE_URL, timeout=60000)

            # Example: adjust this selector to match the OTP container
            messages = self.page.locator("css=div.message-row").all()

            if not messages:
                logging.info("No messages found on OTP page.")
                return

            latest_message = messages[0].inner_text()
            message_id = hash(latest_message)

            if message_id != self.last_message_id:
                self.last_message_id = message_id
                otp_info = self.extract_otp(latest_message)
                self.notifier.send(otp_info)
                logging.info("New OTP message sent.")
            else:
                logging.info("No new OTP detected.")

        except Exception as e:
            self.notifier.send(f"⚠️ Error while checking OTP messages: {e}")
            logging.error(f"Message check error: {e}")

    def extract_otp(self, message_text: str) -> str:
        # Very simple extractor – adjust regex/string parsing as needed
        return f"⭐ **NEW OTP RECEIVED!** ⭐\n\n```\n{message_text}\n```"

    def run(self):
        self.start_browser()
        if not self.login():
            self.stop_browser()
            return

        while self.running:
            self.check_new_messages()
            time.sleep(30)

    def shutdown(self, *args):
        logging.info("Shutdown signal received.")
        self.running = False
        self.stop_browser()


def main():
    notifier = TelegramNotifier(settings.TELEGRAM_BOT_TOKEN, settings.TELEGRAM_CHAT_ID)
    notifier.send("✅ Bot Started Successfully. Initializing configuration and web automation environment.")

    monitor = BrowserMonitor(notifier)

    # graceful shutdown
    signal.signal(signal.SIGINT, monitor.shutdown)
    signal.signal(signal.SIGTERM, monitor.shutdown)

    monitor.run()


if __name__ == "__main__":
    main()
