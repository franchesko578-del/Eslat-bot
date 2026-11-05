"""Do'stga eslatma: havola yaratish va qabul qilish (handlersiz yordamchi)."""
import logging
import secrets
from datetime import datetime
from urllib.parse import quote

from aiogram import Bot
from aiogram.types import LinkPreviewOptions, Message, User

from app.config import Settings
from app.db import Database, iso_z, parse_ts
from app.emoji import CAL, GIFT, MEMO, OK, PEOPLE, WARN
from app.keyboards import main_menu, share_kb
from app.utils import esc, fmt_dt, now_utc

logger = logging.getLogger(__name__)

GIFT_PREFIX = "g_"
MAX_OPEN_SHARES = 20


def gift_token(args: str | None) -> str | None:
    """'/start g_abc123' dan 'abc123' ni ajratadi."""
    if args and args.startswith(GIFT_PREFIX) and len(args) > len(GIFT_PREFIX):
        return args[len(GIFT_PREFIX):]
    return None


async def send_share_card(
    message: Message,
    bot: Bot,
    db: Database,
    settings: Settings,
    user: User,
    text: str,
    remind_at: datetime,
) -> None:
    """Do'st uchun havola yaratib, jo'natuvchiga beradi."""
    if await db.count_open_shares(user.id) >= MAX_OPEN_SHARES:
        await message.answer(
            f"{WARN} Ishlatilmagan havolalar juda ko'p ({MAX_OPEN_SHARES} ta). "
            "Avval do'stlaringiz ularni ochishini kuting.",
            reply_markup=main_menu(),
        )
        return
    token = secrets.token_urlsafe(9)
    await db.create_share(
        {
            "token": token,
            "from_user": user.id,
            "from_name": user.full_name,
            "text": text,
            "remind_at": iso_z(remind_at),
        }
    )
    me = await bot.me()
    link = f"https://t.me/{me.username}?start={GIFT_PREFIX}{token}"
    invite = (
        f"{GIFT} Sizga eslatma tayyorladim. Havolani bosing, "
        "bot kerakli vaqtda eslatadi:"
    )
    share_url = f"https://t.me/share/url?url={quote(link, safe='')}&text={quote(invite)}"
    await message.answer(
        f"{PEOPLE} <b>Do'stga eslatma tayyor!</b>\n\n"
        f"{MEMO} {esc(text)}\n"
        f"{CAL} {fmt_dt(remind_at, settings.tz)}\n\n"
        "Pastdagi tugma bilan do'stingizga yuboring yoki havolani nusxalang:\n"
        f"{link}\n\n"
        "Havola bir kishi uchun ishlaydi.",
        reply_markup=share_kb(share_url),
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


async def accept_gift(
    message: Message, bot: Bot, db: Database, settings: Settings, token: str
) -> None:
    """Havola orqali kelgan odam eslatmani qabul qiladi."""
    user = message.from_user
    share = await db.get_share(token)
    if share is None:
        await message.answer(f"{WARN} Bu havola topilmadi yoki eskirgan.")
        return
    if share.get("claimed_by"):
        await message.answer(f"{WARN} Bu havola allaqachon ishlatilgan.")
        return
    if share["from_user"] == user.id:
        await message.answer(
            f"{PEOPLE} Bu sizning havolangiz. Uni do'stingizga yuboring."
        )
        return
    remind_at = parse_ts(share["remind_at"])
    if remind_at <= now_utc():
        await message.answer(f"{WARN} Bu eslatmaning vaqti o'tib ketgan.")
        return
    if await db.count_active(user.id) >= settings.max_reminders:
        await message.answer(
            f"{WARN} Faol eslatmalaringiz chegaraga yetgan. "
            "Avval keraksizlarini o'chiring, keyin havolani qayta bosing."
        )
        return
    if not await db.claim_share(token, user.id):
        await message.answer(f"{WARN} Bu havola allaqachon ishlatilgan.")
        return
    try:
        await db.create_reminders(
            [
                {
                    "user_id": user.id,
                    "text": share["text"],
                    "remind_at": share["remind_at"],
                    "repeat_type": "once",
                    "sender_name": share.get("from_name"),
                }
            ]
        )
    except Exception:
        logger.exception("Do'st eslatmasini yaratib bo'lmadi (token=%s)", token)
        await db.unclaim_share(token)
        await message.answer(
            f"{WARN} Eslatmani saqlab bo'lmadi. Birozdan keyin havolani qayta bosing."
        )
        return

    sender = esc(share.get("from_name") or "Do'stingiz")
    await message.answer(
        f"{GIFT} <b>{sender}</b> sizga eslatma yubordi!\n\n"
        f"{MEMO} {esc(share['text'])}\n"
        f"{CAL} {fmt_dt(remind_at, settings.tz)}\n\n"
        f"{OK} Shu vaqtda eslataman. Siz ham do'stingizga eslatma yuborishingiz "
        "mumkin: pastdagi \"Do'stga eslatma\" tugmasi.",
        reply_markup=main_menu(),
    )
    try:
        await bot.send_message(
            share["from_user"],
            f"{OK} <b>{esc(user.full_name)}</b> eslatmani qabul qildi:\n"
            f"{MEMO} {esc(share['text'])}",
        )
    except Exception:
        logger.info("Jo'natuvchiga xabar berib bo'lmadi (id=%s)", share["from_user"])
