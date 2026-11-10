"""Foydalanuvchi holati, bloklash, majburiy obuna va xabar jurnali."""
import logging
from datetime import datetime

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from app.alerts import notify_admin
from app.db import Database, is_registered
from app.emoji import WARN
from app.keyboards import subscribe_kb
from app.subscription import check_subscription

logger = logging.getLogger(__name__)

# Obuna tekshiruvidan o'tkazib yuboriladigan tugmalar:
# "sub:" obunani tekshirish, "rm:" kelgan eslatma tugmalari
FREE_CALLBACK_PREFIXES = ("sub:", "rm:")


class TrackUsersMiddleware(BaseMiddleware):
    def __init__(self, db: Database) -> None:
        self.db = db
        self._seen_today = set()  # bugun yozilgan foydalanuvchilar (kuniga bir marta)
        self._seen_day = None

    async def _track_activity(self, user_id: int, tz) -> None:
        """Kunlik faol foydalanuvchilar statistikasi uchun."""
        today = datetime.now(tz).date()
        if self._seen_day != today:
            self._seen_today.clear()
            self._seen_day = today
        if user_id in self._seen_today:
            return
        try:
            await self.db.touch_activity(user_id, today)
            self._seen_today.add(user_id)
        except Exception:
            logger.warning("Faollikni yozib bo'lmadi (user=%s)", user_id)

    async def _gate(self, event, data, user) -> bool:
        """Obuna bo'lmagan bo'lsa, kanal tugmalarini ko'rsatadi. True = to'xtatish."""
        bot = data.get("bot")
        settings = data.get("settings")
        missing, broken = await check_subscription(bot, self.db, user.id)
        for channel, reason in broken:
            await notify_admin(
                bot,
                settings,
                "Majburiy kanalni tekshirib bo'lmadi",
                f"{channel['title']} ({channel['chat_id']})\n{reason}\n"
                "Botni shu kanalga ADMINISTRATOR qiling.",
                key=f"chan:{channel['chat_id']}",
            )
        if not missing:
            return False
        text = (
            "\U0001F4E2 <b>Botdan foydalanish uchun kanalga obuna bo'ling</b>\n\n"
            "1. Pastdagi tugmani bosib obuna bo'ling\n"
            "2. Qaytib kelib \"Obuna bo'ldim\" tugmasini bosing"
        )
        message = event if isinstance(event, Message) else event.message
        if isinstance(event, CallbackQuery):
            await event.answer(f"{WARN} Avval kanalga obuna bo'ling", show_alert=True)
        await message.answer(text, reply_markup=subscribe_kb(missing))
        return True

    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user is None or user.is_bot:
            return await handler(event, data)
        settings = data.get("settings")
        if settings and user.id == settings.admin_id:
            await self._track_activity(user.id, settings.tz)
            return await handler(event, data)
        try:
            record = await self.db.get_user(user.id)
            registered = is_registered(record)
            if settings and registered and not record.get("is_blocked"):
                await self._track_activity(user.id, settings.tz)
            if record and record.get("is_blocked"):
                if isinstance(event, Message):
                    await event.answer("Botdan foydalanishingiz administrator tomonidan cheklangan.")
                return None

            state = data.get("state")
            current = await state.get_state() if state else None

            if isinstance(event, Message):
                # Rozilik va ro'yxatdan o'tish tugagandan keyingina xabar mazmuni qayd etiladi.
                if registered:
                    content = event.text or event.caption or ""
                    if content and not content.startswith("/"):
                        await self.db.log_message(user.id, "foydalanuvchi", "text", content)
                # Ro'yxatdan o'tmagan foydalanuvchini ro'yxatdan o'tish oqimiga yo'naltiramiz.
                if not record and current != "Registration:phone" and not (event.text or "").startswith("/start"):
                    await event.answer("Avval /start tugmasini bosing.")
                    return None

            # Majburiy kanallar (suhbat o'rtasida bo'lmagan foydalanuvchilar uchun)
            if registered and not current:
                free = isinstance(event, CallbackQuery) and (event.data or "").startswith(
                    FREE_CALLBACK_PREFIXES
                )
                if not free and await self._gate(event, data, user):
                    return None
        except Exception:
            logger.exception("Foydalanuvchi nazorati yoki xabar jurnali xatosi")
        return await handler(event, data)
