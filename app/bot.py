"""ESLATMA BOT - asosiy fayl. Ishga tushirish: python -m app.bot"""
import asyncio
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat, ErrorEvent
from aiohttp import web

from app.config import load_settings
from app.db import Database
from app.handlers import get_routers
from app.middlewares import TrackUsersMiddleware
from app.scheduler import run_scheduler

logger = logging.getLogger("app.bot")


def setup_logging() -> None:
    """Loglar ekranga (Render Logs) va logs/bot.log fayliga yoziladi."""
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)
    try:
        os.makedirs("logs", exist_ok=True)
        file_handler = RotatingFileHandler(
            "logs/bot.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except OSError:
        logger.warning("Log faylini yaratib bo'lmadi, faqat ekranga yoziladi")


async def on_error(event: ErrorEvent) -> bool:
    """Kutilmagan xatolarni logga yozadi va foydalanuvchiga xabar beradi."""
    logger.error("Handlerda xatolik: %r", event.exception, exc_info=event.exception)
    update = event.update
    try:
        if update.message:
            await update.message.answer(
                "Xatolik yuz berdi. Birozdan keyin qayta urinib ko'ring."
            )
        elif update.callback_query:
            await update.callback_query.answer(
                "Xatolik yuz berdi. Qayta urinib ko'ring.", show_alert=True
            )
    except Exception:
        logger.exception("Xatolik haqida xabar berib bo'lmadi")
    return True


async def start_health_server(port: int) -> web.AppRunner:
    """Render (va UptimeRobot) tekshiruvi uchun kichik veb-server."""

    async def health(request: web.Request) -> web.Response:
        return web.Response(text="OK")

    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Health server ishga tushdi: port %s", port)
    return runner


async def main() -> None:
    setup_logging()
    settings = load_settings()

    db = Database(settings.supabase_url, settings.supabase_key)
    await db.start()
    runner = None
    scheduler_task = None
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        # Render portni ko'rishi uchun veb-serverni birinchi ishga tushiramiz
        runner = await start_health_server(settings.port)

        await db.ping()
        logger.info("Supabase bilan aloqa yaxshi")
        me = await bot.get_me()
        logger.info("Bot ishga tushmoqda: @%s", me.username)

        dp = Dispatcher(storage=MemoryStorage())
        dp["db"] = db
        dp["settings"] = settings
        tracker = TrackUsersMiddleware(db)
        dp.message.outer_middleware(tracker)
        dp.callback_query.outer_middleware(tracker)
        for router in get_routers():
            dp.include_router(router)
        dp.errors.register(on_error)

        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Botni ishga tushirish"),
                BotCommand(command="help", description="Yordam"),
                BotCommand(command="cancel", description="Bekor qilish"),
            ]
        )
        try:
            await bot.set_my_commands(
                [
                    BotCommand(command="start", description="Botni ishga tushirish"),
                    BotCommand(command="help", description="Yordam"),
                    BotCommand(command="cancel", description="Bekor qilish"),
                    BotCommand(command="admin", description="Admin panel"),
                ],
                scope=BotCommandScopeChat(chat_id=settings.admin_id),
            )
        except Exception:
            logger.warning("Admin buyruqlarini o'rnatib bo'lmadi (admin /start bosmagan)")

        await bot.delete_webhook(drop_pending_updates=True)
        scheduler_task = asyncio.create_task(run_scheduler(bot, db, settings))
        await dp.start_polling(
            bot, allowed_updates=dp.resolve_used_update_types()
        )
    finally:
        if scheduler_task is not None:
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass
        await db.close()
        await bot.session.close()
        if runner is not None:
            await runner.cleanup()
        logger.info("Bot to'xtadi")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi")
