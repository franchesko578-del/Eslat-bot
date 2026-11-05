"""Admin paneli: statistika va hammaga xabar yuborish."""
import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.filters import BaseFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import Settings
from app.db import Database
from app.emoji import BELL, CAL, MEGA, OK, STATS, USER, WARN
from app.keyboards import admin_kb, broadcast_confirm_kb, cancel_menu, main_menu
from app.states import Broadcast
from app.utils import PLAIN, esc, safe_edit, start_of_today_utc

logger = logging.getLogger(__name__)


class IsAdmin(BaseFilter):
    async def __call__(self, event, settings: Settings) -> bool:
        user = getattr(event, "from_user", None)
        return user is not None and user.id == settings.admin_id


router = Router(name="admin")
router.message.filter(F.chat.type == "private", IsAdmin())
router.callback_query.filter(IsAdmin())

_background_tasks = set()


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(f"{USER} <b>Admin panel</b>", reply_markup=admin_kb())


@router.callback_query(F.data == "adm:open")
async def cb_open(call: CallbackQuery) -> None:
    await call.answer()
    await call.message.answer(
        f"{USER} <b>Admin panel</b>", reply_markup=admin_kb()
    )


@router.callback_query(F.data == "adm:stats")
async def cb_stats(call: CallbackQuery, db: Database, settings: Settings) -> None:
    await call.answer()
    s = await db.stats(start_of_today_utc(settings.tz))
    text = (
        f"{STATS} <b>Statistika</b>\n\n"
        f"{USER} Foydalanuvchilar: <b>{s['users_total']}</b> "
        f"(bugun yangi: {s['users_today']})\n"
        f"{BELL} Faol eslatmalar: <b>{s['active']}</b>\n"
        f"{CAL} Jami yaratilgan eslatmalar: {s['reminders_total']}\n"
        f"{OK} Yuborilgan (jami): {s['sent_total']}\n"
        f"{OK} Yuborilgan (bugun): {s['sent_today']}\n"
        f"{WARN} Yuborilmagan (xato): {s['failed_total']}"
    )
    await safe_edit(call, text, admin_kb())


@router.callback_query(F.data == "adm:broadcast")
async def cb_broadcast(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.set_state(Broadcast.text)
    await call.message.answer(
        f"{MEGA} Hamma foydalanuvchilarga yuboriladigan xabar matnini yozing:",
        reply_markup=cancel_menu(),
    )


@router.message(Broadcast.text, PLAIN)
async def got_broadcast_text(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if len(text) > 3500:
        await message.answer(f"{WARN} Xabar juda uzun. Qisqaroq yozing.")
        return
    await state.update_data(text=text)
    await state.set_state(Broadcast.confirm)
    await message.answer(
        f"{MEGA} <b>Xabar ko'rinishi:</b>\n\n{esc(text)}\n\n"
        "Hammaga yuborilsinmi?",
        reply_markup=broadcast_confirm_kb(),
    )


@router.callback_query(Broadcast.confirm, F.data == "bc:no")
async def cb_broadcast_no(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.clear()
    await call.message.answer("Bekor qilindi.", reply_markup=main_menu())


@router.callback_query(Broadcast.confirm, F.data == "bc:yes")
async def cb_broadcast_yes(
    call: CallbackQuery, state: FSMContext, bot: Bot, db: Database
) -> None:
    await call.answer("Yuborish boshlandi")
    data = await state.get_data()
    await state.clear()
    await call.message.answer(
        "Yuborish boshlandi. Tugagach natijani yozaman.",
        reply_markup=main_menu(),
    )
    task = asyncio.create_task(
        _broadcast(bot, db, call.from_user.id, data["text"])
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _broadcast(bot: Bot, db: Database, admin_id: int, text: str) -> None:
    message_text = f"{MEGA} {esc(text)}"
    sent = 0
    failed = 0
    offset = 0
    try:
        while True:
            ids = await db.user_ids(offset, 200)
            if not ids:
                break
            offset += len(ids)
            for user_id in ids:
                try:
                    await bot.send_message(user_id, message_text)
                    sent += 1
                except TelegramRetryAfter as error:
                    await asyncio.sleep(error.retry_after + 1)
                    try:
                        await bot.send_message(user_id, message_text)
                        sent += 1
                    except TelegramAPIError:
                        failed += 1
                except (TelegramForbiddenError, TelegramAPIError):
                    failed += 1
                await asyncio.sleep(0.05)
    except Exception:
        logger.exception("Xabar tarqatishda xatolik")
    await bot.send_message(
        admin_id,
        f"{OK} Tarqatish tugadi.\nYuborildi: {sent}\nYuborilmadi: {failed}",
    )
