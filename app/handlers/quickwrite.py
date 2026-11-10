"""Tez yozish: "ertaga 9:00 dori ichish" deb yozilgan oddiy xabardan eslatma yaratadi."""
import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import Settings
from app.db import Database, iso_z
from app.emoji import CAL, MEMO, OK, REPEAT, TRASH, WARN
from app.handlers.create import MAX_TEXT, ask_time, prompt_date
from app.keyboards import quick_ask_kb, quick_saved_kb
from app.quick import parse_quick
from app.states import CreateReminder
from app.utils import (
    PLAIN,
    esc,
    fmt_dt,
    format_days,
    repeat_extra,
    repeat_label,
    safe_edit,
)

logger = logging.getLogger(__name__)

router = Router(name="quickwrite")
router.message.filter(F.chat.type == "private")


@router.message(StateFilter(None), PLAIN)
async def quick_text(
    message: Message, state: FSMContext, db: Database, settings: Settings
) -> None:
    raw = message.text.strip()
    result = parse_quick(raw, datetime.now(settings.tz), settings.tz)

    if result.error:
        await message.answer(f"{WARN} {result.error} Kelajakdagi vaqtni yozing.")
        return

    # Hech narsa topilmadi: oddiy matn. Eslatma qilishni so'raymiz.
    if not result.found:
        if len(raw) > MAX_TEXT:
            await message.answer(f"{WARN} Matn juda uzun. Eng ko'pi {MAX_TEXT} belgi.")
            return
        await state.update_data(pending_text=raw)
        await message.answer(
            f"{MEMO} <i>{esc(raw[:200])}</i>\n\nEslatma qilaymi?",
            reply_markup=quick_ask_kb(),
        )
        return

    if not result.text:
        await message.answer(
            f"{MEMO} Nima haqida eslatay? Matnni ham yozing:\n"
            "<code>ertaga 9:00 dori ichish</code>"
        )
        return
    if len(result.text) > MAX_TEXT:
        await message.answer(f"{WARN} Matn juda uzun. Eng ko'pi {MAX_TEXT} belgi.")
        return

    user_id = message.from_user.id
    limit = await db.user_limit(user_id, settings.max_reminders)
    if await db.count_active(user_id) >= limit:
        await message.answer(
            f"{WARN} Eslatmalar chegarasiga yetdingiz ({limit} ta). "
            "Keraksizlarini o'chiring yoki do'stlarni taklif qiling."
        )
        return

    repeat = result.repeat or "once"

    # To'liq vaqt topildi: darhol saqlaymiz
    if result.moment is not None:
        start_day = result.moment.astimezone(settings.tz).date()
        extra = repeat_extra(repeat, result.days, result.every, start_day)
        rows = await db.create_reminders(
            [
                {
                    "user_id": user_id,
                    "text": result.text,
                    "remind_at": iso_z(result.moment),
                    "repeat_type": repeat,
                    **extra,
                }
            ]
        )
        await state.clear()
        lines = [
            f"{OK} <b>Saqlandi</b>\n",
            f"{MEMO} {esc(result.text)}",
            f"{CAL} {fmt_dt(result.moment, settings.tz)}",
        ]
        if repeat != "once":
            lines.append(
                f"{REPEAT} "
                f"{repeat_label(repeat, extra.get('repeat_days'), extra.get('repeat_every'))}"
            )
        await message.answer("\n".join(lines), reply_markup=quick_saved_kb(rows[0]["id"]))
        return

    # Qisman topildi: yetishmayotgan qismini tugmalar bilan so'raymiz
    await state.clear()
    await state.update_data(
        text=result.text,
        repeat=repeat,
        days=result.days or [],
        every=result.every,
        recurring_only=False,
        friend=False,
    )
    if result.day is not None:
        await ask_time(message, state, result.day, settings)
    else:
        await state.set_state(CreateReminder.date)
        await prompt_date(message, settings, repeat)


@router.callback_query(F.data == "q:ask")
async def quick_ask(
    call: CallbackQuery, state: FSMContext, db: Database, settings: Settings
) -> None:
    data = await state.get_data()
    text = data.get("pending_text")
    if not text:
        await call.answer("Matn topilmadi. Qayta yozing.", show_alert=True)
        return
    limit = await db.user_limit(call.from_user.id, settings.max_reminders)
    if await db.count_active(call.from_user.id) >= limit:
        await call.answer("Eslatmalar chegarasiga yetdingiz.", show_alert=True)
        return
    await call.answer()
    await state.clear()
    await state.update_data(
        text=text, repeat="once", days=[], every=None, recurring_only=False, friend=False
    )
    await state.set_state(CreateReminder.date)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await prompt_date(call.message, settings, "once")


@router.callback_query(F.data == "q:no")
async def quick_no(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass


@router.callback_query(F.data.startswith("q:del:"))
async def quick_delete(call: CallbackQuery, db: Database) -> None:
    rid = int(call.data.split(":")[2])
    deleted = await db.delete_reminder(rid, call.from_user.id)
    await call.answer("O'chirildi" if deleted else "Eslatma topilmadi")
    await safe_edit(call, f"{TRASH} Eslatma bekor qilindi")
