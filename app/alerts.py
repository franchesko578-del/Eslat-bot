"""Bot xatoga uchrasa, adminga Telegram orqali xabar yuboradi."""
import logging
import time

from aiogram import Bot

from app.config import Settings
from app.emoji import SIREN
from app.utils import esc

logger = logging.getLogger(__name__)

_last_sent: dict = {}
COOLDOWN_SECONDS = 600  # bir xil xato 10 daqiqada bir martadan ko'p yuborilmaydi


async def notify_admin(
    bot: Bot, settings: Settings, title: str, detail: str, key: str = ""
) -> None:
    key = key or title
    now = time.monotonic()
    if now - _last_sent.get(key, -COOLDOWN_SECONDS) < COOLDOWN_SECONDS:
        return
    _last_sent[key] = now
    text = f"{SIREN} <b>{esc(title)}</b>\n<code>{esc(detail[:1500])}</code>"
    try:
        await bot.send_message(settings.admin_id, text)
    except Exception:
        logger.warning("Adminga xato haqida xabar yuborib bo'lmadi")
