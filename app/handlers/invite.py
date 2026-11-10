"""Do'st taklif qilish: shaxsiy havola va qo'shimcha limit."""
from urllib.parse import quote

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import LinkPreviewOptions, Message

from app.config import Settings
from app.db import Database
from app.emoji import BELL, GIFT, LINK, PEOPLE
from app.keyboards import share_kb
from app.sharing import REF_BONUS, REF_MAX_BONUS, REF_PREFIX

router = Router(name="invite")
router.message.filter(F.chat.type == "private")


@router.message(F.text.endswith("Do'st taklif qilish"))
async def menu_invite(
    message: Message, state: FSMContext, bot: Bot, db: Database, settings: Settings
) -> None:
    await state.clear()
    uid = message.from_user.id
    me = await bot.me()
    link = f"https://t.me/{me.username}?start={REF_PREFIX}{uid}"
    count = await db.count_referrals(uid)
    limit = await db.user_limit(uid, settings.max_reminders)
    invite = (
        f"{BELL} Men eslatma botidan foydalanyapman. Nimani unutmasligingiz "
        "kerak bo'lsa yozasiz, vaqtida o'zi eslatadi. Sinab ko'ring:"
    )
    share_url = f"https://t.me/share/url?url={quote(link, safe='')}&text={quote(invite)}"
    await message.answer(
        f"{GIFT} <b>Do'st taklif qilish</b>\n\n"
        f"Do'stingiz sizning havolangiz orqali botga kirib, raqamini tasdiqlasa, "
        f"sizga <b>+{REF_BONUS} eslatma limiti</b> beriladi "
        f"(eng ko'pi +{REF_MAX_BONUS}).\n\n"
        f"{PEOPLE} Taklif qilganlar: <b>{count}</b>\n"
        f"{BELL} Sizning limitingiz: <b>{limit}</b> ta eslatma\n\n"
        f"{LINK} {link}",
        reply_markup=share_kb(share_url, "Do'stlarga yuborish"),
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
