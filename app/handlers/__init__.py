"""Barcha handler (buyruq va tugma ishlovchilari) routerlari."""
from aiogram import Router

from app.handlers import (
    admin,
    create,
    fallback,
    manage,
    settings_menu,
    start,
)


def get_routers() -> list:
    # Tartib muhim: fallback eng oxirida turishi kerak
    return [
        start.router,
        admin.router,
        create.router,
        manage.router,
        settings_menu.router,
        fallback.router,
    ]
