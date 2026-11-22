import os
import time
import requests
from bs4 import BeautifulSoup

class TelegramNotifier:
    def __init__(self, bot_token: str | None = None, chat_id: str | None = None):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is not set. Please set it in your .env file.")
        if not self.chat_id:
            raise ValueError("TELEGRAM_CHAT_ID is not set. Please set it in your .env file.")

        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        Send a message via Telegram Bot API with HTML parse_mode and plain-text fallback.
        """
        # Truncate if exceeding Telegram limit of 4096 characters
        if len(text) > 4000:
            text = text[:3950] + "\n\n<i>[Message truncated due to size limit]</i>"

        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False
        }

        try:
            resp = requests.post(self.api_url, json=payload, timeout=15)
            if resp.status_code == 200:
                return True

            data = resp.json()
            description = data.get("description", "")
            print(f"[Telegram] Failed with HTTP {resp.status_code}: {description}")

            # If HTML parsing failed, fallback to plain text
            if "can't parse entities" in description.lower() or parse_mode == "HTML":
                print("[Telegram] Retrying message in plain text format...")
                soup = BeautifulSoup(text, "html.parser")
                plain_text = soup.get_text(separator="\n").strip()
                fallback_payload = {
                    "chat_id": self.chat_id,
                    "text": plain_text,
                    "disable_web_page_preview": False
                }
                retry_resp = requests.post(self.api_url, json=fallback_payload, timeout=15)
                return retry_resp.status_code == 200

            return False
        except Exception as e:
            print(f"[Telegram] Connection error sending message: {e}")
            return False

    def send_test_message(self) -> bool:
        """Send a test handshake message to verify bot setup."""
        test_msg = (
            "🛰️ <b>AI Intern Radar is Online!</b>\n\n"
            "Your Telegram Bot connection has been successfully established.\n"
            "You will receive automatic alerts whenever new AI/ML internships are detected."
        )
        return self.send_message(test_msg)
