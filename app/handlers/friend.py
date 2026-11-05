"""Do'stga eslatma: menyu tugmasi va tayyor eslatmani do'stga yuborish."""
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import Settings
from app.db import Database, parse_ts
from app.handlers.create import begin
from app.sharing import send_share_card
from app.utils import now_utc

router = Router(name="friend")
router.message.filter(F.chat.type == "private")


@router.message(F.text.endswith("Do'stga eslatma"))
async def menu_friend(
    message: Message, state: FSMContext, db: Database, settings: Settings
) -> None:
    await begin(message, state, db, settings, False, friend=True)


@router.callback_query(F.data.startswith("fr:share:"))
async def share_existing(
    call: CallbackQuery, bot: Bot, db: Database, settings: Settings
) -> None:
    rid = int(call.data.split(":")[2])
    row = await db.get_reminder(rid, call.from_user.id)
    if row is None:
        await call.answer("Eslatma topilmadi.", show_alert=True)
        return
    remind_at = parse_ts(row["remind_at"])
    if remind_at <= now_utc():
        await call.answer("Bu eslatmaning vaqti o'tib ketgan.", show_alert=True)
        return
    await call.answer()
    await send_share_card(
        call.message, bot, db, settings, call.from_user, row["text"], remind_at
    )
