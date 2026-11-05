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
from app.emoji import BELL, CAL, CHART, MEGA, OK, STATS, USER, WARN
from app.keyboards import admin_kb, broadcast_confirm_kb, cancel_menu, main_menu
from app.states import Broadcast, AddChannel
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


@router.callback_query(F.data == "adm:daily")
async def cb_daily(call: CallbackQuery, db: Database, settings: Settings) -> None:
    await call.answer()
    days = await db.daily_stats(settings.tz, 7)  # [bugun, kecha, ...]
    top = max((d["active"] for d in days), default=0) or 1
    lines = [
        f"{CHART} <b>Kunlik faollik</b> (oxirgi 7 kun)\n",
        "Faol = shu kuni botga yozgan yoki tugma bosganlar.\n",
    ]
    for d in days:
        bar = "▇" * max(1 if d["active"] else 0, round(d["active"] / top * 10))
        lines.append(
            f"<b>{d['day'].strftime('%d.%m')}</b>  {USER} {d['active']} {bar}\n"
            f"      yangi: {d['new']} · yaratilgan: {d['created']} · "
            f"yuborilgan: {d['sent']}"
        )
    average = sum(d["active"] for d in days) / len(days)
    lines.append(f"\nO'rtacha faol (kuniga): <b>{average:.1f}</b>")
    await safe_edit(call, "\n".join(lines), admin_kb())


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



# ---------- Foydalanuvchilar ----------
@router.callback_query(F.data.startswith("adm:users:"))
async def cb_users(call: CallbackQuery, db: Database):
    await call.answer()
    page = max(0, int(call.data.rsplit(":", 1)[1]))
    rows, total = await db.list_users(page * 10, 10)
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    for row in rows:
        title = row.get("full_name") or str(row["telegram_id"])
        status = "⛔" if row.get("is_blocked") else "👤"
        buttons.append([InlineKeyboardButton(text=f"{status} {title[:35]} · {row['telegram_id']}", callback_data=f"adm:user:{row['telegram_id']}:{page}")])
    nav = []
    if page > 0: nav.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"adm:users:{page-1}"))
    if (page + 1) * 10 < total: nav.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"adm:users:{page+1}"))
    if nav: buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="⬅️ Admin panel", callback_data="adm:open")])
    await call.message.answer(f"<b>Foydalanuvchilar</b>\nJami: {total}\nSahifa: {page+1}", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("adm:user:"))
async def cb_user_detail(call: CallbackQuery, db: Database):
    await call.answer()
    _, _, uid, page = call.data.split(":")
    user = await db.get_user(int(uid))
    if not user:
        await call.message.answer("Foydalanuvchi topilmadi."); return
    status = "Bloklangan" if user.get("is_blocked") else "Faol"
    text = (f"<b>Foydalanuvchi ma'lumotlari</b>\n\nID: <code>{uid}</code>\n"
            f"Ism: {esc(user.get('full_name') or '—')}\nUsername: @{esc(user.get('username') or 'yoq')}\n"
            f"Telefon: <code>{esc(user.get('phone') or '—')}</code>\nHolat: {status}\n"
            f"Ro'yxatdan o'tgan: {esc(user.get('created_at') or '—')}")
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    action = "adm:unblock" if user.get("is_blocked") else "adm:block"
    label = "Blokdan chiqarish" if user.get("is_blocked") else "Bloklash"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=f"{action}:{uid}:{page}")],
        [InlineKeyboardButton(text="Xabarlar tarixi", callback_data=f"adm:logs:{uid}")],
        [InlineKeyboardButton(text="⬅️ Ro'yxat", callback_data=f"adm:users:{page}")]])
    await call.message.answer(text, reply_markup=kb)

@router.callback_query(F.data.startswith("adm:block:"))
@router.callback_query(F.data.startswith("adm:unblock:"))
async def cb_block_user(call: CallbackQuery, db: Database):
    action, uid, page = call.data.split(":")
    blocked = action == "adm:block"
    await db.set_blocked(int(uid), blocked)
    await call.answer("Foydalanuvchi bloklandi" if blocked else "Blokdan chiqarildi", show_alert=True)

@router.callback_query(F.data.startswith("adm:logs:"))
async def cb_user_logs(call: CallbackQuery, db: Database):
    await call.answer()
    uid = int(call.data.split(":")[2])
    rows = await db.get_message_logs(uid, 20)
    if not rows:
        await call.message.answer("Bu foydalanuvchining saqlangan xabarlari yo'q."); return
    lines = [f"<b>So'nggi xabarlar — {uid}</b>"]
    for row in rows:
        stamp = str(row.get("created_at", ""))[:16].replace("T", " ")
        lines.append(f"\n{stamp} · {row.get('direction')} ({row.get('message_type')})\n{esc(row.get('content') or '')[:500]}")
    await call.message.answer("\n".join(lines)[:4000])

# ---------- Majburiy obuna kanallari ----------
@router.callback_query(F.data == "adm:channels")
async def cb_channels(call: CallbackQuery, db: Database):
    await call.answer()
    rows = await db.list_channels()
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = [[InlineKeyboardButton(text=f"🗑 {r['title']} ({r['chat_id']})", callback_data=f"adm:chdel:{r['id']}")] for r in rows]
    buttons.append([InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="adm:chadd")])
    buttons.append([InlineKeyboardButton(text="⬅️ Admin panel", callback_data="adm:open")])
    await call.message.answer("<b>Majburiy obuna kanallari</b>\nKanalni o'chirish uchun uning tugmasini bosing.", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data == "adm:chadd")
async def cb_channel_add(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(AddChannel.chat_id)
    await call.message.answer("Kanal ID yoki @username yuboring (masalan: @kanal_nomi).")

@router.message(AddChannel.chat_id, PLAIN)
async def channel_id(message: Message, state: FSMContext):
    await state.update_data(chat_id=message.text.strip())
    await state.set_state(AddChannel.title)
    await message.answer("Kanal nomini yuboring.")

@router.message(AddChannel.title, PLAIN)
async def channel_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(AddChannel.invite)
    await message.answer("Kanalga taklif havolasini yuboring (yoki - yuboring).")

@router.message(AddChannel.invite, PLAIN)
async def channel_invite(message: Message, state: FSMContext, db: Database):
    data = await state.get_data(); await state.clear()
    link = None if message.text.strip() == "-" else message.text.strip()
    await db.add_channel(data["chat_id"], data["title"], link)
    await message.answer("Kanal ro'yxatga qo'shildi. Botni kanalga administrator qilib qo'ying.", reply_markup=admin_kb())

@router.callback_query(F.data.startswith("adm:chdel:"))
async def cb_channel_delete(call: CallbackQuery, db: Database):
    await call.answer()
    await db.remove_channel(int(call.data.split(":")[2]))
    await call.message.answer("Kanal o'chirildi.", reply_markup=admin_kb())
