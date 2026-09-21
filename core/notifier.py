"""
core/notifier.py — ລະບົບສົ່ງແຈ້ງເຕືອນໄປຍັງໂທລະສັບ (WhatsApp / Telegram / Webhook)

ຮອງຮັບ:
1. WhatsApp (CallMeBot) - ແຈ້ງເຕືອນເຂົ້າ WhatsApp ສ່ວນຕົວຟຣີ
2. Telegram Bot - ແຈ້ງເຕືອນ ແລະ ສົ່ງຮູບພາບເຂົ້າ Telegram
3. Custom Webhook (Discord / Slack / n8n)
"""

import threading
import urllib.parse
from datetime import datetime
from typing import Dict, Any, Optional
import requests


class MobileNotifier:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.whatsapp_cfg = config.get("whatsapp_notify", {})
        self.telegram_cfg = config.get("telegram_notify", {})

    def send_async(self, message: str, image_path: Optional[str] = None):
        """ສົ່ງແຈ້ງເຕືອນແບບ Asynchronous ໃນ Background Thread ເພື່ອບໍ່ໃຫ້ Bot ຊັກຊ້າ."""
        t = threading.Thread(target=self._send_all, args=(message, image_path), daemon=True)
        t.start()

    def _send_all(self, message: str, image_path: Optional[str] = None):
        # 1. WhatsApp CallMeBot
        if self.whatsapp_cfg.get("enabled", False):
            phone = str(self.whatsapp_cfg.get("phone", "")).strip()
            apikey = str(self.whatsapp_cfg.get("apikey", "")).strip()
            if phone and apikey:
                self._send_callmebot(phone, apikey, message)

        # 2. Telegram Bot
        if self.telegram_cfg.get("enabled", False):
            token = str(self.telegram_cfg.get("bot_token", "")).strip()
            chat_id = str(self.telegram_cfg.get("chat_id", "")).strip()
            if token and chat_id:
                self._send_telegram(token, chat_id, message, image_path)

    def _send_callmebot(self, phone: str, apikey: str, text: str) -> bool:
        try:
            clean_phone = phone.replace("+", "").replace(" ", "").replace("-", "")
            encoded_text = urllib.parse.quote(text)
            url = f"https://api.callmebot.com/whatsapp.php?phone={clean_phone}&text={encoded_text}&apikey={apikey}"
            resp = requests.get(url, timeout=12)
            return resp.status_code == 200
        except Exception as e:
            print(f"[Notifier] CallMeBot error: {e}")
            return False

    def _send_telegram(self, token: str, chat_id: str, text: str, image_path: Optional[str] = None) -> bool:
        try:
            if image_path:
                url = f"https://api.telegram.org/bot{token}/sendPhoto"
                with open(image_path, "rb") as f:
                    resp = requests.post(
                        url,
                        data={"chat_id": chat_id, "caption": text[:1024], "parse_mode": "Markdown"},
                        files={"photo": f},
                        timeout=20
                    )
                    return resp.status_code == 200
            else:
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                resp = requests.post(
                    url,
                    json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                    timeout=12
                )
                return resp.status_code == 200
        except Exception as e:
            print(f"[Notifier] Telegram error: {e}")
            return False

    def notify_upload_success(self, video_title: str, page_name: str, duration_sec: float = 0):
        ts = datetime.now().strftime("%H:%M:%S")
        msg = (
            f"✅ *[Reels Bot] ອັບໂຫຼດວິດີໂອສຳເລັດ!* 🚀\n\n"
            f"🎬 *ຊື່ເລື່ອງ:* {video_title}\n"
            f"📄 *Page:* {page_name}\n"
            f"⏱ *ເວລາ:* {ts}\n"
        )
        self.send_async(msg)

    def notify_upload_failed(self, video_title: str, page_name: str, error_msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        msg = (
            f"❌ *[Reels Bot] ອັບໂຫຼດລົ້ມເຫຼວ!* ⚠️\n\n"
            f"🎬 *ວິດີໂອ:* {video_title}\n"
            f"📄 *Page:* {page_name}\n"
            f"❗ *ສາເຫດ:* {error_msg[:200]}\n"
            f"⏱ *ເວລາ:* {ts}\n"
        )
        self.send_async(msg)

    def notify_cta_posted(self, title: str, page_name: str, image_path: Optional[str] = None):
        ts = datetime.now().strftime("%H:%M:%S")
        msg = (
            f"📸 *[Reels Bot] ໂພສຮູບພາບ AI ເຊີນຊວນຕິດຕາມແລ້ວ!* 🎉\n\n"
            f"⭐ *ຫົວຂໍ້:* {title}\n"
            f"📄 *Page:* {page_name}\n"
            f"🎯 *ເປົ້າໝາຍ:* Facebook Creator Goals (Followers)\n"
            f"⏱ *ເວລາ:* {ts}\n"
        )
        self.send_async(msg, image_path=image_path)

    def notify_monitor_started(self, local_url: str, public_url: str = ""):
        msg = (
            f"🌐 *[Reels Bot] ເລີ່ມຕົ້ນລະບົບ Mobile Monitor ແລ້ວ!*\n\n"
            f"📱 *ເຂົ້າເບິ່ງຜ່ານໂທລະສັບ:*\n"
            f"• ໃນ Wi-Fi: {local_url}\n"
        )
        if public_url:
            msg += f"• ທາງນອກ (4G/5G): {public_url}\n"
        msg += "\nທ່ານສາມາດກວດເບິ່ງສະຖານະ % ແລະ ຄິວວິດີໂອໄດ້ຕະຫຼອດເວລາ!"
        self.send_async(msg)
