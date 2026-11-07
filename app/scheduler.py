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
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)

from app.alerts import notify_admin
from app.config import Settings
from app.db import Database, DatabaseError, parse_ts
from app.emoji import BELL, CAL, CLOCK, HOURGLASS, MEMO, PEOPLE, REPEAT, SUN
from app.keyboards import reminder_kb
from app.utils import esc, fmt_dt, next_occurrence, now_utc, row_repeat, short

logger = logging.getLogger(__name__)

BATCH_SIZE = 50
MAX_FAILS = 5
LATE_AFTER_SECONDS = 300


def build_message(row: dict, old_time, next_time, settings: Settings) -> str:
    text = f"{BELL} <b>ESLATMA</b>\n\n{MEMO} {esc(row['text'])}"
    if row.get("sender_name"):
        text += f"\n{PEOPLE} {esc(row['sender_name'])} yubordi"
    late = (now_utc() - old_time).total_seconds() > LATE_AFTER_SECONDS
    if late:
        text += f"\n{CLOCK} Reja: {fmt_dt(old_time, settings.tz)}"
    if next_time is not None:
        text += (
            f"\n{REPEAT} {row_repeat(row)} · keyingisi: "
            f"{fmt_dt(next_time, settings.tz)}"
        )
    return text


async def _send(bot: Bot, user_id: int, text: str, rid: int) -> None:
    markup = reminder_kb(rid)  # 5/10/15 min, 1 soat, ertaga, bajarildi
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
    next_time = next_occurrence(
        old_time,
        row["repeat_type"],
        now_utc(),
        settings.tz,
        row.get("repeat_days"),
        row.get("repeat_every"),
    )

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


class _Cache:
    """Foydalanuvchi sozlamalarini 60 soniya eslab turadi (bazani tez-tez so'ramaslik uchun)."""

    def __init__(self) -> None:
        self.pre: list = []
        self.pre_at = None
        self.digest: list = []
        self.digest_at = None


def _stale(stamp, now) -> bool:
    return stamp is None or (now - stamp).total_seconds() > 60


async def process_pre_alerts(
    bot: Bot, db: Database, settings: Settings, cache: _Cache
) -> None:
    """Eslatmadan oldin ("10 daqiqadan keyin: ...") ogohlantirish yuboradi."""
    now = now_utc()
    if _stale(cache.pre_at, now):
        cache.pre = await db.users_with_pre()
        cache.pre_at = now
    minutes = {u["telegram_id"]: int(u["pre_minutes"]) for u in cache.pre}
    if not minutes:
        return
    until = now + timedelta(minutes=max(minutes.values()))
    for row in await db.pre_candidates(list(minutes), now, until):
        window = timedelta(minutes=minutes.get(row["user_id"], 0))
        remind_at = parse_ts(row["remind_at"])
        if not window or remind_at - now > window:
            continue
        # Avval belgilaymiz: ikki marta yuborilmasin
        await db.mark_pre_sent(row["id"])
        if parse_ts(row["created_at"]) > remind_at - window:
            continue  # eslatma allaqachon ogohlantirish oynasida yaratilgan
        left = max(1, round((remind_at - now).total_seconds() / 60))
        text = (
            f"{HOURGLASS} <b>{left} daqiqadan keyin</b>\n"
            f"{MEMO} {esc(short(row['text'], 300))}\n"
            f"{CLOCK} {fmt_dt(remind_at, settings.tz)}"
        )
        try:
            await bot.send_message(row["user_id"], text)
        except (TelegramForbiddenError, TelegramBadRequest):
            pass
        await asyncio.sleep(0.05)


async def process_digests(
    bot: Bot, db: Database, settings: Settings, cache: _Cache
) -> None:
    """Har ertalab "Bugungi eslatmalar" ro'yxatini yuboradi."""
    now = now_utc()
    if _stale(cache.digest_at, now):
        cache.digest = await db.users_with_digest()
        cache.digest_at = now
    local_now = datetime.now(settings.tz)
    today = local_now.date().isoformat()
    day_end = (
        datetime.combine(local_now.date() + timedelta(days=1), datetime.min.time(), tzinfo=settings.tz)
    )
    for user in cache.digest:
        hour = int(user["digest_hour"])
        if user.get("last_digest_date") == today:
            continue
        if not (hour <= local_now.hour < hour + 6):
            continue
        user["last_digest_date"] = today
        await db.update_user(user["telegram_id"], {"last_digest_date": today})
        rows = await db.reminders_between(user["telegram_id"], now, day_end)
        if not rows:
            continue
        lines = [f"{SUN} <b>Bugungi eslatmalar</b> ({len(rows)} ta)\n"]
        for row in rows:
            when = parse_ts(row["remind_at"]).astimezone(settings.tz).strftime("%H:%M")
            mark = f" {REPEAT}" if row.get("repeat_type") != "once" else ""
            lines.append(f"{BELL} <b>{when}</b>  {esc(short(row['text'], 60))}{mark}")
        try:
            await bot.send_message(user["telegram_id"], "\n".join(lines))
        except (TelegramForbiddenError, TelegramBadRequest):
            pass
        await asyncio.sleep(0.05)


async def run_scheduler(bot: Bot, db: Database, settings: Settings) -> None:
    logger.info("Rejalovchi ishga tushdi (har %s soniyada)", settings.check_interval)
    cache = _Cache()
    while True:
        handled = 0
        try:
            handled = await process_due(bot, db, settings)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.exception("Rejalovchida xatolik")
            await notify_admin(
                bot, settings, "Rejalovchida xatolik", repr(error), key="scheduler"
            )
        for job, name in (
            (process_pre_alerts, "Oldindan ogohlantirish"),
            (process_digests, "Ertalabki ro'yxat"),
        ):
            try:
                await job(bot, db, settings, cache)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.exception("%s ishida xatolik", name)
                await notify_admin(
                    bot, settings, f"{name}: xatolik", repr(error), key=name
                )
        if handled < BATCH_SIZE:
            await asyncio.sleep(settings.check_interval)
