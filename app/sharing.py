"""Do'stga eslatma: havola yaratish va qabul qilish (handlersiz yordamchi)."""
import logging
import secrets
from datetime import datetime
from urllib.parse import quote

from aiogram import Bot
from aiogram.types import LinkPreviewOptions, Message, User

from app.config import Settings
from app.db import Database, iso_z, parse_ts
from app.emoji import CAL, GIFT, LINK, MEMO, OK, PEOPLE, WARN
from app.keyboards import main_menu, share_kb
from app.utils import esc, fmt_dt, now_utc

logger = logging.getLogger(__name__)

GIFT_PREFIX = "g_"
REF_PREFIX = "ref_"
MAX_OPEN_SHARES = 20
REF_BONUS = 10  # har bir taklif qilingan do'st uchun qo'shimcha limit
REF_MAX_BONUS = 200


def ref_id(args: str | None) -> int | None:
    """'/start ref_123' dan 123 ni ajratadi (do'st taklif qilish havolasi)."""
    if args and args.startswith(REF_PREFIX) and args[len(REF_PREFIX):].isdigit():
        return int(args[len(REF_PREFIX):])
    return None


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
            f"{WARN} Do'stlaringiz hali ochmagan havolalar juda ko'p ({MAX_OPEN_SHARES} ta). "
            "Ular ochgunicha kuting.",
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
    when = fmt_dt(remind_at, settings.tz)
    invite = (
        f"{GIFT} {user.full_name} sizga eslatma yubordi:\n"
        f"{MEMO} {text[:150]}\n{CAL} {when}\n\n"
        "Qabul qilish uchun bosing:"
    )
    share_url = f"https://t.me/share/url?url={quote(link, safe='')}&text={quote(invite)}"
    await message.answer(
        f"{OK} <b>Tayyor!</b>\n\n"
        f"{MEMO} {esc(text)}\n"
        f"{CAL} {when}\n\n"
        f"{PEOPLE} Endi pastdagi tugmani bosib, shu eslatmani do'stingizga yuboring. "
        "U bosib botni ochsa, eslatma uning telefoniga o'rnatiladi. "
        "U \"Bajarildi\" bossa, sizga xabar keladi.",
        reply_markup=share_kb(share_url, "Do'stga yuborish"),
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
            f"{PEOPLE} Bu sizning havolangiz. Uni do'stingizga yuboring, "
            "o'zingizga emas."
        )
        return
    remind_at = parse_ts(share["remind_at"])
    if remind_at <= now_utc():
        await message.answer(f"{WARN} Bu eslatmaning vaqti o'tib ketgan.")
        return
    limit = await db.user_limit(user.id, settings.max_reminders)
    if await db.count_active(user.id) >= limit:
        await message.answer(
            f"{WARN} Eslatmalaringiz chegarasiga yetgan. Keraksizlarini o'chirib, "
            "havolani qayta bosing."
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
                    "sender_id": share["from_user"],
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
        f"{GIFT} <b>{sender}</b> sizga eslatma yubordi\n\n"
        f"{MEMO} {esc(share['text'])}\n"
        f"{CAL} {fmt_dt(remind_at, settings.tz)}\n\n"
        f"{OK} Qabul qilindi. Shu vaqtda sizga eslataman.",
        reply_markup=main_menu(),
    )
    try:
        await bot.send_message(
            share["from_user"],
            f"{OK} <b>{esc(user.full_name)}</b> eslatmani qabul qildi\n"
            f"{MEMO} {esc(share['text'])}",
        )
    except Exception:
        logger.info("Jo'natuvchiga xabar berib bo'lmadi (id=%s)", share["from_user"])


async def reward_referrer(
    bot: Bot, db: Database, settings: Settings, referrer_id: int, friend: User
) -> None:
    """Do'sti qo'shilgan odamga qo'shimcha eslatma limiti beradi."""
    referrer = await db.get_user(referrer_id)
    if not referrer:
        return
    bonus = int(referrer.get("bonus_limit") or 0)
    if bonus >= REF_MAX_BONUS:
        return
    bonus = min(REF_MAX_BONUS, bonus + REF_BONUS)
    await db.update_user(referrer_id, {"bonus_limit": bonus})
    try:
        await bot.send_message(
            referrer_id,
            f"{GIFT} <b>{esc(friend.full_name)}</b> sizning havolangiz orqali qo'shildi!\n"
            f"{OK} Limitingiz +{REF_BONUS} oshdi: endi {settings.max_reminders + bonus} ta eslatma.",
        )
    except Exception:
        logger.info("Taklif qilganga xabar yuborib bo'lmadi (id=%s)", referrer_id)
