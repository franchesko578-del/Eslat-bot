"""Foydalanuvchi holati, bloklash va shaffof xabar jurnalini boshqarish."""
import logging
from aiogram import BaseMiddleware
from aiogram.types import Message
from datetime import datetime

from app.db import Database, is_registered

logger = logging.getLogger(__name__)

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
            if settings and is_registered(record) and not record.get("is_blocked"):
                await self._track_activity(user.id, settings.tz)
            if record and record.get("is_blocked"):
                if isinstance(event, Message):
                    await event.answer("Botdan foydalanishingiz administrator tomonidan cheklangan.")
                return None
            if isinstance(event, Message):
                # Rozilik va ro'yxatdan o'tish tugagandan keyingina xabar mazmuni qayd etiladi.
                if is_registered(record):
                    content = event.text or event.caption or ""
                    if content and not content.startswith("/"):
                        await self.db.log_message(user.id, "foydalanuvchi", "text", content)
                # Ro'yxatdan o'tmagan foydalanuvchini ro'yxatdan o'tish oqimiga yo'naltiramiz.
                state = data.get("state")
                current = await state.get_state() if state else None
                registration_states = {"Registration:phone"}
                if not record and current not in registration_states and not (event.text or "").startswith("/start"):
                    await event.answer("Avval ro'yxatdan o'tish uchun /start buyrug'ini bosing.")
                    return None
                # Majburiy kanallar: bot har bir kanalda a'zo ekanini tekshiradi.
                if is_registered(record):
                    channels = await self.db.list_channels()
                    missing = []
                    bot = data.get("bot")
                    for channel in channels:
                        try:
                            member = await bot.get_chat_member(channel["chat_id"], user.id)
                            if member.status not in ("creator", "administrator", "member"):
                                missing.append(channel)
                        except Exception:
                            missing.append(channel)
                    if missing and not current:
                        links = "\n".join(f"• {c['title']}: {c.get('invite_link') or c['chat_id']}" for c in missing)
                        await event.answer("Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:\n" + links + "\n\nObuna bo'lgach /start yuboring.")
                        return None
        except Exception:
            logger.exception("Foydalanuvchi nazorati yoki xabar jurnali xatosi")
        return await handler(event, data)
