# config.py
import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Website
WEBSITE_URL = os.getenv("WEBSITE_URL", "https://ivas.com/login")
WEBSITE_USERNAME = os.getenv("WEBSITE_USERNAME")
WEBSITE_PASSWORD = os.getenv("WEBSITE_PASSWORD")
OTP_PAGE_URL = os.getenv("OTP_PAGE_URL", "https://www.ivasms.com/portal/sms/received")
