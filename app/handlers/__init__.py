"""Barcha handler (buyruq va tugma ishlovchilari) routerlari."""
from aiogram import Router

from app.handlers import (
    admin,
    create,
    fallback,
    friend,
    invite,
    manage,
    quickwrite,
    reminder_actions,
    settings_menu,
    start,
)


def get_routers() -> list:
    # Tartib muhim: fallback eng oxirida turishi kerak
    return [
        start.router,
        admin.router,
        create.router,
        friend.router,
        invite.router,
        manage.router,
        reminder_actions.router,
        settings_menu.router,
        quickwrite.router,
        fallback.router,
    ]
