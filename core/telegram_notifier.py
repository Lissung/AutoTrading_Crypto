import requests
import json
import os
from core.logger import logger

class TelegramNotifier:
    def __init__(self):
        self.token = None
        self.chat_id = None
        self._load_config()

    def _load_config(self):
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                self.token = config.get("TELEGRAM_BOT_TOKEN", "")
                self.chat_id = config.get("TELEGRAM_CHAT_ID", "")
        except Exception as e:
            logger.error(f"Failed to load config for telegram: {e}")

    def send_message(self, text):
        if not self.token or not self.chat_id or "여기에" in self.token:
            return # 설정이 안되어 있으면 무시
            
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML"
        }
        try:
            response = requests.post(url, json=payload, timeout=5)
            if response.status_code != 200:
                logger.error(f"Telegram API Error: {response.text}")
        except Exception as e:
            logger.error(f"Failed to send telegram message: {e}")
