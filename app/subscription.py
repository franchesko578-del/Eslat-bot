"""Majburiy obuna: foydalanuvchi kanallarga a'zomi, shuni tekshiradi."""
import logging
import time

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)

from app.db import Database

logger = logging.getLogger(__name__)

OK_SECONDS = 90  # a'zo bo'lgan foydalanuvchi qayta tekshirilmaydi
CHANNELS_SECONDS = 60  # kanallar ro'yxati xotirada turadi

_ok_until: dict = {}
_channels: dict = {"at": 0.0, "rows": []}


def clear_cache() -> None:
    """Admin kanal qo'shganda yoki o'chirganda chaqiriladi."""
    _ok_until.clear()
    _channels["at"] = 0.0


async def _channel_rows(db: Database) -> list:
    now = time.monotonic()
    if now - _channels["at"] > CHANNELS_SECONDS:
        _channels["rows"] = await db.list_channels()
        _channels["at"] = now
    return _channels["rows"]


def _is_member(member) -> bool:
    if member.status in ("creator", "administrator", "member"):
        return True
    return member.status == "restricted" and bool(getattr(member, "is_member", False))


async def check_subscription(
    bot: Bot, db: Database, user_id: int, force: bool = False
):
    """(obuna bo'lmagan kanallar, tekshirib bo'lmagan kanallar) qaytaradi.

    Tekshirib bo'lmagan kanal (masalan, bot admin emas) foydalanuvchini
    to'sib qo'ymaydi, lekin admin ogohlantiriladi.
    """
    if not force and _ok_until.get(user_id, 0) > time.monotonic():
        return [], []
    missing, broken = [], []
    for channel in await _channel_rows(db):
        try:
            member = await bot.get_chat_member(channel["chat_id"], user_id)
            if not _is_member(member):
                missing.append(channel)
        except TelegramRetryAfter:
            continue
        except (TelegramBadRequest, TelegramForbiddenError) as error:
            logger.warning("Kanalni tekshirib bo'lmadi (%s): %s", channel["chat_id"], error)
            broken.append((channel, str(error)))
    if not missing:
        _ok_until[user_id] = time.monotonic() + OK_SECONDS
    return missing, broken
