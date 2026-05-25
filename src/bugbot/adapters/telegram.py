import logging
from typing import Optional
import requests
from ..config.settings import get_settings

log = logging.getLogger(__name__)

def send_text(text: str, parse_mode: Optional[str] = None) -> dict:
    s = get_settings()
    url = f"https://api.telegram.org/bot{s.bot_token}/sendMessage"
    data: dict = {"chat_id": s.chat_id, "text": text}
    if parse_mode:
        data["parse_mode"] = parse_mode
    if s.thread_id is not None:   # para grupos con temas
        data["message_thread_id"] = s.thread_id

    resp = requests.post(url, data=data, timeout=20)
    resp.raise_for_status()
    body = resp.json()
    log.info(
        "Mensaje enviado chat_id=%s ok=%s message_id=%s",
        s.chat_id, body.get("ok"), body.get("result", {}).get("message_id")
    )
    return body