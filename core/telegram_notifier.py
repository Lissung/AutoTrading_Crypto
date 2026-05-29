import requests
import json
import os
from core.logger import logger

class TelegramNotifier:
    def __init__(self):
        self.token = None
        self.chat_id = None
        self._last_update_id = None
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

    def get_latest_command(self):
        """텔레그램에서 가장 최근에 받은 명령어를 조회합니다. (/stop 킬스위치용)"""
        if not self.token or not self.chat_id or "여기에" in self.token:
            return None
        try:
            url = f"https://api.telegram.org/bot{self.token}/getUpdates"
            params = {"limit": 5, "timeout": 0}
            if self._last_update_id is not None:
                params["offset"] = self._last_update_id + 1

            response = requests.get(url, params=params, timeout=5)
            if response.status_code != 200:
                return None

            data = response.json()
            if not data.get("ok") or not data.get("result"):
                return None

            latest_command = None
            for update in data["result"]:
                update_id = update.get("update_id")
                self._last_update_id = max(self._last_update_id or 0, update_id)

                message = update.get("message", {})
                # 본인 채팅방에서 온 메시지만 처리
                if str(message.get("chat", {}).get("id", "")) != str(self.chat_id):
                    continue

                text = message.get("text", "").strip().lower()
                if text in ["/stop", "/start"]:
                    latest_command = text

            return latest_command
        except Exception as e:
            logger.error(f"Failed to get telegram commands: {e}")
            return None
