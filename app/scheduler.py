"""Eslatmalarni belgilangan vaqtda yuboruvchi rejalovchi.

Ishlash tartibi:
1. Har bir necha soniyada bazadan vaqti kelgan eslatmalar olinadi.
2. Har bir eslatma avval bazada 'band qilinadi' (claim). Faqat band qilgan
   jarayon yuboradi, shuning uchun eslatma ikki marta ketmaydi.
3. Yuborilgandan keyin natija logga yoziladi.
Hamma narsa bazada saqlanadi, shuning uchun bot qayta ishga tushsa ham
eslatmalar yo'qolmaydi.
"""
import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)

from app.config import Settings
from app.db import Database, DatabaseError, parse_ts
from app.emoji import BELL, CLOCK, PEOPLE, REPEAT
from app.keyboards import reminder_kb
from app.utils import esc, fmt_dt, next_occurrence, now_utc, repeat_label

logger = logging.getLogger(__name__)

BATCH_SIZE = 50
MAX_FAILS = 5
LATE_AFTER_SECONDS = 300


def build_message(row: dict, old_time, next_time, settings: Settings) -> str:
    text = f"{BELL} <b>ESLATMA</b>\n\n{esc(row['text'])}"
    if row.get("sender_name"):
        text += f"\n\n{PEOPLE} {esc(row['sender_name'])} yubordi"
    late = (now_utc() - old_time).total_seconds() > LATE_AFTER_SECONDS
    if late:
        text += (
            f"\n\n{CLOCK} Rejalashtirilgan vaqt: "
            f"{fmt_dt(old_time, settings.tz)}"
        )
    if next_time is not None:
        text += (
            f"\n\n{REPEAT} {repeat_label(row['repeat_type'])}. "
            f"Keyingi eslatma: {fmt_dt(next_time, settings.tz)}"
        )
    return text


async def _send(bot: Bot, user_id: int, text: str, rid: int) -> None:
    markup = reminder_kb(rid)  # Bajarildi / 10 daqiqadan keyin / 1 soatdan keyin
    try:
        await bot.send_message(user_id, text, reply_markup=markup)
    except TelegramRetryAfter as error:
        await asyncio.sleep(error.retry_after + 1)
        await bot.send_message(user_id, text, reply_markup=markup)


async def _log(db: Database, rid: int, uid: int, ok: bool, err=None) -> None:
    try:
        await db.add_log(rid, uid, ok, err)
    except Exception:
        logger.exception("Eslatma logini yozib bo'lmadi (id=%s)", rid)


async def handle_one(
    bot: Bot, db: Database, settings: Settings, row: dict
) -> None:
    rid = row["id"]
    user_id = row["user_id"]
    old_time = parse_ts(row["remind_at"])
    next_time = next_occurrence(old_time, row["repeat_type"], now_utc())

    try:
        claimed = await db.claim(rid, old_time, next_time)
    except DatabaseError:
        logger.exception("Eslatmani band qilib bo'lmadi (id=%s)", rid)
        return
    if not claimed:
        return  # Boshqa jarayon allaqachon oldi yoki foydalanuvchi o'zgartirdi

    text = build_message(row, old_time, next_time, settings)
    try:
        await _send(bot, user_id, text, rid)
    except (TelegramForbiddenError, TelegramBadRequest) as error:
        # Foydalanuvchi botni bloklagan yoki chat topilmadi: qayta urinmaymiz
        logger.warning("Yuborib bo'lmadi (id=%s, user=%s): %s", rid, user_id, error)
        await _log(db, rid, user_id, False, str(error))
        try:
            await db.set_status(rid, "failed")
        except Exception:
            logger.exception("Holatni o'zgartirib bo'lmadi (id=%s)", rid)
    except Exception as error:
        logger.exception("Yuborishda xatolik (id=%s)", rid)
        await _log(db, rid, user_id, False, repr(error))
        fails = int(row.get("fail_count") or 0) + 1
        try:
            await db.revert(rid, old_time, fails, fails >= MAX_FAILS)
        except Exception:
            logger.exception("Eslatmani qaytarib bo'lmadi (id=%s)", rid)
    else:
        logger.info("Eslatma yuborildi (id=%s, user=%s)", rid, user_id)
        await _log(db, rid, user_id, True)
        await asyncio.sleep(0.05)  # Telegram limitidan oshmaslik uchun


async def process_due(bot: Bot, db: Database, settings: Settings) -> int:
    rows = await db.due_reminders(now_utc(), BATCH_SIZE)
    for row in rows:
        await handle_one(bot, db, settings, row)
    return len(rows)


async def run_scheduler(bot: Bot, db: Database, settings: Settings) -> None:
    logger.info("Rejalovchi ishga tushdi (har %s soniyada)", settings.check_interval)
    while True:
        handled = 0
        try:
            handled = await process_due(bot, db, settings)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Rejalovchida xatolik")
        if handled < BATCH_SIZE:
            await asyncio.sleep(settings.check_interval)
