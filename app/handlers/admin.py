"""Admin paneli: statistika va hammaga xabar yuborish."""
import asyncio
import logging
import re

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
from app import subscription
from app.db import Database, DatabaseError
from app.emoji import BELL, CAL, CHART, MEGA, OK, STATS, USER, WARN
from app.keyboards import (
    BLUE,
    GREEN,
    RED,
    admin_kb,
    broadcast_confirm_kb,
    btn,
    cancel_menu,
    main_menu,
)
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
    from aiogram.types import InlineKeyboardMarkup
    buttons = []
    for row in rows:
        title = row.get("full_name") or str(row["telegram_id"])
        status = "⛔" if row.get("is_blocked") else "👤"
        buttons.append([btn(f"{status} {title[:35]} · {row['telegram_id']}", f"adm:user:{row['telegram_id']}:{page}", RED if row.get("is_blocked") else BLUE)])
    nav = []
    if page > 0: nav.append(btn("⬅️ Oldingi", f"adm:users:{page-1}"))
    if (page + 1) * 10 < total: nav.append(btn("Keyingi ➡️", f"adm:users:{page+1}", GREEN))
    if nav: buttons.append(nav)
    buttons.append([btn("⬅️ Admin panel", "adm:open", RED)])
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
    from aiogram.types import InlineKeyboardMarkup
    action = "adm:unblock" if user.get("is_blocked") else "adm:block"
    label = "Blokdan chiqarish" if user.get("is_blocked") else "Bloklash"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [btn(label, f"{action}:{uid}:{page}", GREEN if user.get("is_blocked") else RED)],
        [btn("📜 Xabarlar tarixi", f"adm:logs:{uid}", BLUE)],
        [btn("⬅️ Ro'yxat", f"adm:users:{page}", RED)]])
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
def _channels_text(rows: list) -> str:
    if not rows:
        return (
            "\U0001F4E2 <b>Majburiy obuna kanallari</b>\n\n"
            "Hozircha kanal yo'q. Kanal qo'shsangiz, foydalanuvchilar avval "
            "shu kanalga obuna bo'lishi kerak bo'ladi."
        )
    lines = [f"\U0001F4E2 <b>Majburiy obuna kanallari</b> ({len(rows)} ta)\n"]
    lines += [f"{i}. {esc(r['title'])}" for i, r in enumerate(rows, start=1)]
    lines.append("\nO'chirish uchun kanal tugmasini bosing.")
    return "\n".join(lines)


def _channels_kb(rows: list):
    from aiogram.types import InlineKeyboardMarkup
    buttons = [[btn(f"\U0001F5D1 {r['title']}", f"adm:chdel:{r['id']}", RED)] for r in rows]
    buttons.append([btn("\u2795 Kanal qo'shish", "adm:chadd", GREEN)])
    buttons.append([btn("\u2b05\ufe0f Admin panel", "adm:open", BLUE)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "adm:channels")
async def cb_channels(call: CallbackQuery, db: Database):
    await call.answer()
    rows = await db.list_channels()
    await safe_edit(call, _channels_text(rows), _channels_kb(rows))


@router.callback_query(F.data == "adm:chadd")
async def cb_channel_add(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(AddChannel.chat_id)
    await call.message.answer(
        "\u2795 <b>Kanal qo'shish</b>\n\n"
        "1\ufe0f\u20e3 Botni kanalga <b>administrator</b> qiling\n"
        "2\ufe0f\u20e3 Kanal manzilini yuboring: <code>@kanal_nomi</code>\n\n"
        "Yopiq kanal bo'lsa, kanaldan istalgan xabarni shu yerga <b>forward</b> qiling.\n"
        "Bekor qilish: /cancel"
    )


def parse_channel(text: str):
    """@nom, t.me/nom havolasi, nom yoki raqamli ID ni tanib oladi."""
    value = text.strip()
    match = re.match(r"^(?:https?://)?(?:t|telegram)\.me/([A-Za-z][A-Za-z0-9_]{3,})/?$", value)
    if match:
        return "@" + match.group(1)
    if re.fullmatch(r"@[A-Za-z][A-Za-z0-9_]{3,}", value):
        return value
    if re.fullmatch(r"-?\d{5,}", value):
        return int(value)
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,}", value):
        return "@" + value
    return None


@router.message(AddChannel.chat_id)
async def channel_resolve(message: Message, state: FSMContext, bot: Bot, db: Database):
    """Kanalni o'zi topadi: nomi, ID si va havolasini avtomatik oladi."""
    ident = None
    origin = getattr(message, "forward_origin", None)
    if origin is not None and getattr(origin, "type", None) == "channel":
        ident = origin.chat.id
    elif message.text:
        ident = parse_channel(message.text)
    if ident is None:
        await message.answer(
            f"{WARN} Tushunmadim. <code>@kanal_nomi</code> yuboring yoki "
            "kanaldan bitta xabarni forward qiling."
        )
        return
    try:
        chat = await bot.get_chat(ident)
    except TelegramAPIError:
        await message.answer(
            f"{WARN} Kanal topilmadi. Manzil to'g'riligini tekshiring.\n"
            "Yopiq kanal bo'lsa, undan bitta xabarni forward qiling."
        )
        return
    if chat.type not in ("channel", "supergroup", "group"):
        await message.answer(f"{WARN} Bu kanal yoki guruh emas. Boshqa manzil yuboring.")
        return
    me = await bot.me()
    try:
        member = await bot.get_chat_member(chat.id, me.id)
        is_admin = member.status in ("administrator", "creator")
    except TelegramAPIError:
        is_admin = False
    if not is_admin:
        await message.answer(
            f"{WARN} Bot <b>{esc(chat.title or '')}</b> kanalida administrator emas.\n\n"
            "Kanal sozlamalari \u2192 Administratorlar \u2192 botni qo'shing, "
            "keyin manzilni qayta yuboring."
        )
        return
    link = f"https://t.me/{chat.username}" if chat.username else None
    if link is None:
        try:
            link = (await bot.create_chat_invite_link(chat.id)).invite_link
        except TelegramAPIError:
            link = getattr(chat, "invite_link", None)
    try:
        await db.add_channel(str(chat.id), chat.title or str(chat.id), link)
    except DatabaseError as error:
        text = str(error).lower()
        if "23505" in text or "duplicate" in text or "409" in text:
            await message.answer(f"{WARN} Bu kanal allaqachon qo'shilgan.")
        else:
            logger.exception("Kanalni saqlab bo'lmadi")
            await message.answer(f"{WARN} Bazaga saqlab bo'lmadi: {esc(str(error)[:200])}")
        await state.clear()
        return
    subscription.clear_cache()
    await state.clear()
    rows = await db.list_channels()
    await message.answer(
        f"{OK} Kanal qo'shildi: <b>{esc(chat.title or '')}</b>\n\n"
        "Endi foydalanuvchilar avval shu kanalga obuna bo'lishi kerak.",
        reply_markup=main_menu(),
    )
    await message.answer(_channels_text(rows), reply_markup=_channels_kb(rows))


@router.callback_query(F.data.startswith("adm:chdel:"))
async def cb_channel_delete(call: CallbackQuery, db: Database):
    await db.remove_channel(int(call.data.split(":")[2]))
    subscription.clear_cache()
    await call.answer("O'chirildi")
    rows = await db.list_channels()
    await safe_edit(call, _channels_text(rows), _channels_kb(rows))
