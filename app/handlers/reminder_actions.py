"""Eslatma kelganda chiqadigan tugmalar: kechiktirish va "Bajarildi"."""
import logging
from datetime import timedelta

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from app.config import Settings
from app.db import Database, iso_z, parse_ts
from app.emoji import BELL, OK, SUN
from app.utils import fmt_dt, now_utc

logger = logging.getLogger(__name__)

router = Router(name="reminder_actions")

SNOOZE_MINUTES = (5, 10, 15, 60)


async def _mark(call: CallbackQuery, note: str) -> None:
    """Tugmalarni olib tashlab, xabar oxiriga izoh qo'shadi."""
    try:
        await call.message.edit_text(
            f"{call.message.html_text}\n\n{note}", reply_markup=None
        )
    except TelegramBadRequest as error:
        logger.info("Eslatma xabarini tahrirlab bo'lmadi: %s", error)


@router.callback_query(F.data.startswith("rm:done:"))
async def cb_done(call: CallbackQuery) -> None:
    await call.answer("Barakalla! \U0001F44F")
    await _mark(call, f"{OK} <b>Bajarildi</b>")


async def _reschedule(
    call: CallbackQuery, db: Database, settings: Settings, rid: int, when_fn
) -> None:
    """Eslatma nusxasini yangi vaqtga qo'yadi (asl takrorlash buzilmaydi)."""
    row = await db.get_reminder_any(rid, call.from_user.id)
    if row is None:
        await call.answer("Eslatma topilmadi (o'chirilgan bo'lishi mumkin)", show_alert=True)
        return
    if await db.count_active(call.from_user.id) >= settings.max_reminders:
        await call.answer("Eslatmalar chegarasiga yetdingiz", show_alert=True)
        return
    when = when_fn(row).replace(second=0, microsecond=0)
    new_row = {
        "user_id": call.from_user.id,
        "text": row["text"],
        "remind_at": iso_z(when),
        "repeat_type": "once",
        "pre_sent": True,  # kechiktirilganda oldindan ogohlantirish kerak emas
    }
    if row.get("sender_name"):
        new_row["sender_name"] = row["sender_name"]
    await db.create_reminders([new_row])
    await call.answer("Qayta eslataman")
    await _mark(call, f"{BELL} Qayta eslataman: <b>{fmt_dt(when, settings.tz)}</b>")


@router.callback_query(F.data.startswith("rm:snz:"))
async def cb_snooze(call: CallbackQuery, db: Database, settings: Settings) -> None:
    parts = call.data.split(":")
    rid, minutes = int(parts[2]), int(parts[3])
    if minutes not in SNOOZE_MINUTES:
        await call.answer()
        return
    await _reschedule(
        call, db, settings, rid, lambda row: now_utc() + timedelta(minutes=minutes)
    )


@router.callback_query(F.data.startswith("rm:tom:"))
async def cb_tomorrow(call: CallbackQuery, db: Database, settings: Settings) -> None:
    rid = int(call.data.split(":")[2])

    def tomorrow(row: dict):
        # Bir martalik: asl vaqtning ertangi kuni. Takroriy: hozirdan 24 soat.
        if row.get("repeat_type") == "once":
            candidate = parse_ts(row["remind_at"]) + timedelta(days=1)
            while candidate <= now_utc():
                candidate += timedelta(days=1)
            return candidate
        return now_utc() + timedelta(days=1)

    await _reschedule(call, db, settings, rid, tomorrow)
