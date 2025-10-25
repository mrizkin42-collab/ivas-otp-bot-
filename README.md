# Telegram OTP Monitor (Playwright + Python)

This repository contains a production-ready Telegram bot that logs into a virtual-number website (like `ivas.com`), monitors the user's message inbox for OTPs, and forwards them to your Telegram chat — without an official API (uses headless browser automation).

> **Important:** You must have permission from the website owner to automate/scrape their site. Use responsibly.

---

## Features
- Uses **Playwright** (headless) for robust login & scraping.
- Sends status updates to Telegram for:
  - Bot started
  - Login success / failure
  - New OTP received
  - Errors & restarts
- Keeps track of last-sent message to avoid duplicates (persisted to `last_seen.json`).
- Designed to be deployed on platforms such as Render / Docker / GitHub Actions (see notes).

---

## Files
- `main.py` — main application and monitoring loop
- `config.py` — load environment variables & selectors
- `requirements.txt` — Python dependencies
- `.env.example` — example environment variables & selectors
- `.gitignore`
- `last_seen.json` — created at runtime (ignored by git)

---

## Setup (local)
1. Clone:
```bash
git clone https://github.com/mrizkin42-collab/ivas-otp-bot.git
cd ivas-otp-bot

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

playwright install --with-deps

python main.py


You should receive a Telegram message:
✅ Bot Started Successfully. Initializing configuration and web automation environment.

If login is successful:
🌐 Login Successful! Session established. Starting continuous OTP monitoring loop.
