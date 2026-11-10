"""Sozlamalar bo'limi."""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import Settings
from app.db import Database
from app.emoji import BELL, GEAR, GLOBE, HOURGLASS, ID, WARN
from app.keyboards import confirm_delall_kb, pre_kb, pre_label, settings_kb
from app.utils import HELP_TEXT, safe_edit

router = Router(name="settings")
router.message.filter(F.chat.type == "private")

PRE_OPTIONS = (0, 5, 10, 15, 30, 60)


async def _render(user_id: int, db: Database, settings: Settings):
    """Sozlamalar matni va tugmalari."""
    user = await db.get_user(user_id) or {}
    active = await db.count_active(user_id)
    limit = await db.user_limit(user_id, settings.max_reminders)
    pre = int(user.get("pre_minutes") or 0)
    text = (
        f"{GEAR} <b>Sozlamalar</b>\n\n"
        f"{ID} ID: <code>{user_id}</code>\n"
        f"{GLOBE} Vaqt zonasi: {settings.timezone_name}\n"
        f"{BELL} Faol eslatmalar: {active} / {limit}\n"
        f"{HOURGLASS} Oldindan ogohlantirish: {pre_label(pre)}"
    )
    return text, settings_kb(user_id == settings.admin_id, pre), pre


async def _show_settings(call: CallbackQuery, db: Database, settings: Settings) -> None:
    text, keyboard, _ = await _render(call.from_user.id, db, settings)
    await safe_edit(call, text, keyboard)


@router.message(F.text.endswith("Sozlamalar"))
async def menu_settings(
    message: Message, state: FSMContext, db: Database, settings: Settings
) -> None:
    await state.clear()
    text, keyboard, _ = await _render(message.from_user.id, db, settings)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "set:help")
async def cb_help(call: CallbackQuery) -> None:
    await call.answer()
    await call.message.answer(HELP_TEXT)


# ---------- Oldindan ogohlantirish ----------
@router.callback_query(F.data == "set:pre")
async def cb_pre(call: CallbackQuery, db: Database, settings: Settings) -> None:
    await call.answer()
    _, _, pre = await _render(call.from_user.id, db, settings)
    await safe_edit(
        call,
        f"{HOURGLASS} <b>Oldindan ogohlantirish</b>\n\n"
        "Eslatma vaqtidan oldin qisqa xabar keladi, masalan "
        "\"10 daqiqadan keyin: dori ichish\". Qancha oldin ogohlantiray?",
        pre_kb(pre),
    )


@router.callback_query(F.data.startswith("pre:"))
async def cb_pre_set(call: CallbackQuery, db: Database, settings: Settings) -> None:
    value = call.data.split(":")[1]
    if not value.isdigit() or int(value) not in PRE_OPTIONS:
        await call.answer()
        return
    await db.update_user(call.from_user.id, {"pre_minutes": int(value)})
    await call.answer("Saqlandi")
    await _show_settings(call, db, settings)


# ---------- Hammasini o'chirish ----------
@router.callback_query(F.data == "set:delall")
async def cb_delete_all_ask(call: CallbackQuery) -> None:
    await call.answer()
    await safe_edit(
        call,
        f"{WARN} <b>Barcha faol eslatmalar o'chiriladi.</b> Davom etasizmi?",
        confirm_delall_kb(),
    )


@router.callback_query(F.data == "set:delall_yes")
async def cb_delete_all_yes(
    call: CallbackQuery, db: Database, settings: Settings
) -> None:
    count = await db.delete_all_active(call.from_user.id)
    await call.answer(f"{count} ta eslatma o'chirildi", show_alert=True)
    await _show_settings(call, db, settings)


@router.callback_query(F.data == "set:cancel")
async def cb_cancel(call: CallbackQuery, db: Database, settings: Settings) -> None:
    await call.answer()
    await _show_settings(call, db, settings)
