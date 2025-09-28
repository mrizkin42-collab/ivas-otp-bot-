"""
config.py
Load environment variables and basic configuration for the bot.
"""

from dotenv import load_dotenv
import os

load_dotenv()

class Settings:
    # Required credentials (set as environment variables)
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID")) if os.getenv("TELEGRAM_CHAT_ID") else None

    WEBSITE_URL = os.getenv("WEBSITE_URL")  # e.g. https://ivas.com/login
    WEBSITE_USERNAME = os.getenv("WEBSITE_USERNAME")
    WEBSITE_PASSWORD = os.getenv("WEBSITE_PASSWORD")
    OTP_PAGE_URL = os.getenv("OTP_PAGE_URL")  # e.g. https://ivas.com/my-messages (optional)

    # Monitoring interval (seconds)
    CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "30"))

    # --- Selectors (update to match the target site). You may set these in .env or edit here ---
    # Common defaults — these are placeholders and most likely must be changed.
    USERNAME_INPUT_SELECTOR = os.getenv("USERNAME_INPUT_SELECTOR", 'input[name="username"]')
    PASSWORD_INPUT_SELECTOR = os.getenv("PASSWORD_INPUT_SELECTOR", 'input[name="password"]')
    SUBMIT_BUTTON_SELECTOR = os.getenv("SUBMIT_BUTTON_SELECTOR", 'button[type="submit"]')

    # Where messages/OTPs are displayed
    MESSAGES_CONTAINER_SELECTOR = os.getenv("MESSAGES_CONTAINER_SELECTOR", 'div.messages')
    MESSAGE_ITEM_SELECTOR = os.getenv("MESSAGE_ITEM_SELECTOR", '.message-item')
    MESSAGE_ID_ATTR = os.getenv("MESSAGE_ID_ATTR", 'data-id')

    # Inside each message item — placeholders
    NUMBER_SELECTOR = os.getenv("NUMBER_SELECTOR", '.number')
    SERVICE_SELECTOR = os.getenv("SERVICE_SELECTOR", '.platform')
    MESSAGE_TEXT_SELECTOR = os.getenv("MESSAGE_TEXT_SELECTOR", '.message-text')
    TIMESTAMP_SELECTOR = os.getenv("TIMESTAMP_SELECTOR", '.time')

settings = Settings()
