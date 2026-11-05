"""Eslatma kelganda chiqadigan tugmalar: Bajarildi va keyinroq eslatish."""
import logging
from datetime import timedelta

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from app.config import Settings
from app.db import Database, iso_z
from app.emoji import BELL, OK
from app.utils import now_utc

logger = logging.getLogger(__name__)

router = Router(name="reminder_actions")

SNOOZE_LABELS = {10: "10 daqiqadan keyin", 60: "1 soatdan keyin"}


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
    await call.answer("Barakalla!")
    await _mark(call, f"{OK} Bajarildi")


@router.callback_query(F.data.startswith("rm:snz:"))
async def cb_snooze(call: CallbackQuery, db: Database, settings: Settings) -> None:
    parts = call.data.split(":")
    rid, minutes = int(parts[2]), int(parts[3])
    if minutes not in SNOOZE_LABELS:
        await call.answer()
        return
    row = await db.get_reminder_any(rid, call.from_user.id)
    if row is None:
        await call.answer("Eslatma topilmadi (o'chirilgan bo'lishi mumkin).", show_alert=True)
        return
    if await db.count_active(call.from_user.id) >= settings.max_reminders:
        await call.answer("Faol eslatmalar chegarasiga yetdingiz.", show_alert=True)
        return

    when = (now_utc() + timedelta(minutes=minutes)).replace(second=0, microsecond=0)
    new_row = {
        "user_id": call.from_user.id,
        "text": row["text"],
        "remind_at": iso_z(when),
        "repeat_type": "once",
    }
    if row.get("sender_name"):
        new_row["sender_name"] = row["sender_name"]
    await db.create_reminders([new_row])

    local = when.astimezone(settings.tz).strftime("%H:%M")
    await call.answer(f"{SNOOZE_LABELS[minutes]} eslataman")
    await _mark(call, f"{BELL} Qayta eslataman: {local}")
