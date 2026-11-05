"""Tugmalar (reply va inline klaviaturalar)."""
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.db import parse_ts
from app.emoji import (
    BACK,
    CROSS,
    GEAR,
    INFO,
    LIST,
    MEGA,
    NEXT,
    OK,
    PENCIL,
    PLUS,
    REPEAT,
    STATS,
    TRASH,
    USER,
)
from app.utils import fmt_dt, short

BTN_CREATE = f"{PLUS} Eslatma yaratish"
BTN_LIST = f"{LIST} Eslatmalarim"
BTN_RECURRING = f"{REPEAT} Takroriy eslatma"
BTN_SETTINGS = f"{GEAR} Sozlamalar"
BTN_CANCEL = f"{CROSS} Bekor qilish"


def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CREATE), KeyboardButton(text=BTN_LIST)],
            [
                KeyboardButton(text=BTN_RECURRING),
                KeyboardButton(text=BTN_SETTINGS),
            ],
        ],
        resize_keyboard=True,
    )


def cancel_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
    )


def repeat_kb(recurring_only: bool) -> InlineKeyboardMarkup:
    rows = []
    if not recurring_only:
        rows.append([_btn("Bir marta", "rep:once")])
    rows.append([_btn("Har kuni", "rep:daily")])
    rows.append([_btn("Har hafta", "rep:weekly")])
    if not recurring_only:
        rows.append([_btn("Maxsus sana va vaqt", "rep:custom")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def date_kb(today_str: str, tomorrow_str: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(f"Bugun ({today_str})", "date:today"),
                _btn(f"Ertaga ({tomorrow_str})", "date:tomorrow"),
            ]
        ]
    )


def list_kb(rows: list, page: int, total: int, page_size: int, tz):
    keyboard = []
    start = page * page_size
    for index, row in enumerate(rows, start=start + 1):
        when = fmt_dt(parse_ts(row["remind_at"]), tz)
        label = f"{index}. {when} {short(row['text'], 22)}"
        keyboard.append([_btn(label, f"r:view:{row['id']}:{page}")])
    nav = []
    if page > 0:
        nav.append(_btn(f"{BACK} Oldingi", f"list:{page - 1}"))
    if start + page_size < total:
        nav.append(_btn(f"Keyingi {NEXT}", f"list:{page + 1}"))
    if nav:
        keyboard.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def detail_kb(reminder_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(f"{PENCIL} Matn", f"r:et:{reminder_id}:{page}"),
                _btn(f"{PENCIL} Vaqt", f"r:ed:{reminder_id}:{page}"),
            ],
            [_btn(f"{TRASH} O'chirish", f"r:del:{reminder_id}:{page}")],
            [_btn(f"{BACK} Orqaga", f"list:{page}")],
        ]
    )


def confirm_delete_kb(reminder_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(f"{OK} Ha, o'chirish", f"r:delyes:{reminder_id}:{page}"),
                _btn("Yo'q", f"r:view:{reminder_id}:{page}"),
            ]
        ]
    )


def settings_kb(is_admin: bool) -> InlineKeyboardMarkup:
    rows = [
        [_btn(f"{INFO} Yordam", "set:help")],
        [_btn(f"{TRASH} Barcha eslatmalarni o'chirish", "set:delall")],
    ]
    if is_admin:
        rows.append([_btn(f"{USER} Admin panel", "adm:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_delall_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(f"{OK} Ha, hammasini o'chir", "set:delall_yes"),
                _btn("Yo'q", "set:cancel"),
            ]
        ]
    )


def admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(f"{STATS} Statistika", "adm:stats")],
            [_btn(f"{MEGA} Hammaga xabar yuborish", "adm:broadcast")],
        ]
    )


def broadcast_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(f"{OK} Yuborish", "bc:yes"),
                _btn(f"{CROSS} Bekor qilish", "bc:no"),
            ]
        ]
    )
