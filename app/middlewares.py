"""Yangi foydalanuvchilarni bazaga yozib boruvchi oraliq qatlam."""
import asyncio
import logging

from aiogram import BaseMiddleware

from app.db import Database

logger = logging.getLogger(__name__)


class TrackUsersMiddleware(BaseMiddleware):
    """Foydalanuvchi birinchi marta yozganda uni orqa fonda saqlaydi.
    Shuning uchun bot javobi sekinlashmaydi."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.seen = set()
        self._tasks = set()

    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user is not None and not user.is_bot and user.id not in self.seen:
            self.seen.add(user.id)
            task = asyncio.create_task(self._save(user))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        return await handler(event, data)

    async def _save(self, user) -> None:
        try:
            await self.db.upsert_user(
                user.id, user.full_name or "", user.username
            )
        except Exception:
            # Keyingi xabarda qayta uriniladi
            self.seen.discard(user.id)
            logger.exception("Foydalanuvchini saqlab bo'lmadi: %s", user.id)
