"""Sozlamalar bo'limi."""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import Settings
from app.db import Database
from app.emoji import BELL, GEAR, GLOBE, OK, USER, WARN
from app.keyboards import confirm_delall_kb, settings_kb
from app.utils import HELP_TEXT, safe_edit

router = Router(name="settings")
router.message.filter(F.chat.type == "private")


async def settings_text(user_id: int, db: Database, settings: Settings) -> str:
    active = await db.count_active(user_id)
    return (
        f"{GEAR} <b>Sozlamalar</b>\n\n"
        f"{USER} Sizning ID: <code>{user_id}</code>\n"
        f"{GLOBE} Vaqt zonasi: {settings.timezone_name}\n"
        f"{BELL} Faol eslatmalar: {active} ta "
        f"(eng ko'pi {settings.max_reminders} ta)\n\n"
        "Sana: YYYY-MM-DD, vaqt: HH:MM"
    )


@router.message(F.text.endswith("Sozlamalar"))
async def menu_settings(
    message: Message, state: FSMContext, db: Database, settings: Settings
) -> None:
    await state.clear()
    user_id = message.from_user.id
    text = await settings_text(user_id, db, settings)
    await message.answer(
        text, reply_markup=settings_kb(user_id == settings.admin_id)
    )


@router.callback_query(F.data == "set:help")
async def cb_help(call: CallbackQuery) -> None:
    await call.answer()
    await call.message.answer(HELP_TEXT)


@router.callback_query(F.data == "set:delall")
async def cb_delete_all_ask(call: CallbackQuery) -> None:
    await call.answer()
    await safe_edit(
        call,
        f"{WARN} Barcha faol eslatmalaringiz o'chiriladi. Davom etasizmi?",
        confirm_delall_kb(),
    )


@router.callback_query(F.data == "set:delall_yes")
async def cb_delete_all_yes(
    call: CallbackQuery, db: Database, settings: Settings
) -> None:
    count = await db.delete_all_active(call.from_user.id)
    await call.answer(f"{count} ta eslatma o'chirildi", show_alert=True)
    text = await settings_text(call.from_user.id, db, settings)
    await safe_edit(
        call, text, settings_kb(call.from_user.id == settings.admin_id)
    )


@router.callback_query(F.data == "set:cancel")
async def cb_cancel(
    call: CallbackQuery, db: Database, settings: Settings
) -> None:
    await call.answer(f"{OK}")
    text = await settings_text(call.from_user.id, db, settings)
    await safe_edit(
        call, text, settings_kb(call.from_user.id == settings.admin_id)
    )
