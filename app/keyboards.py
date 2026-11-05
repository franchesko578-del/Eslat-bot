"""Tugmalar (reply va inline klaviaturalar)."""
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.db import parse_ts
from datetime import date, datetime
from typing import Optional

from app.emoji import (
    BACK,
    BELL,
    CHART,
    CROSS,
    GEAR,
    INFO,
    LIST,
    MEGA,
    NEXT,
    OK,
    PEOPLE,
    PENCIL,
    PLUS,
    REPEAT,
    SEND,
    STATS,
    TRASH,
    USER,
)
from app.utils import fmt_dt, short

BTN_CREATE = f"{PLUS} Eslatma yaratish"
BTN_LIST = f"{LIST} Eslatmalarim"
BTN_RECURRING = f"{REPEAT} Takroriy eslatma"
BTN_SETTINGS = f"{GEAR} Sozlamalar"
BTN_FRIEND = f"{PEOPLE} Do'stga eslatma"
BTN_CANCEL = f"{CROSS} Bekor qilish"


def _btn(text: str, data: str, style: Optional[str] = None) -> InlineKeyboardButton:
    """style: "primary" (ko'k), "success" (yashil), "danger" (qizil).
    Eski Telegram ilovalari rangni e'tiborsiz qoldiradi, tugma baribir ishlaydi."""
    extra = {"style": style} if style else {}
    return InlineKeyboardButton(text=text, callback_data=data, **extra)


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CREATE), KeyboardButton(text=BTN_LIST)],
            [
                KeyboardButton(text=BTN_RECURRING),
                KeyboardButton(text=BTN_SETTINGS),
            ],
            [KeyboardButton(text=BTN_FRIEND)],
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


def hour_kb() -> InlineKeyboardMarkup:
    """Soat: 00 dan 23 gacha."""
    buttons = [_btn(f"{h:02d}", f"th:{h}") for h in range(24)]
    rows = [buttons[i : i + 6] for i in range(0, 24, 6)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def minute_kb() -> InlineKeyboardMarkup:
    """Minut: 00 dan 59 gacha."""
    buttons = [_btn(f"{m:02d}", f"tm:{m}") for m in range(60)]
    rows = [buttons[i : i + 6] for i in range(0, 60, 6)]
    rows.append([_btn(f"{BACK} Soatni o'zgartirish", "tb:hour")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reminder_kb(reminder_id: int) -> InlineKeyboardMarkup:
    """Eslatma kelganda ko'rinadigan ko'k tugmalar."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(f"{BELL} 5 minutdan keyin", f"rm:snz:{reminder_id}:5", "primary")],
            [_btn(f"{BELL} 10 minutdan keyin", f"rm:snz:{reminder_id}:10", "primary")],
            [_btn(f"{BELL} 15 minutdan keyin", f"rm:snz:{reminder_id}:15", "primary")],
            [_btn(f"{OK} Bajarildi", f"rm:done:{reminder_id}", "primary")],
        ]
    )


def quick_saved_kb(reminder_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(f"{TRASH} Bekor qilish", f"q:del:{reminder_id}"),
                _btn(f"{PEOPLE} Do'stga yuborish", f"fr:share:{reminder_id}"),
            ]
        ]
    )


def quick_ask_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(f"{BELL} Eslatma qilish", "q:ask"),
                _btn("Yo'q", "q:no"),
            ]
        ]
    )


def share_kb(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=f"{SEND} Do'stga yuborish", url=url)]]
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
            [_btn(f"{CHART} Kunlik faollik", "adm:daily")],
            [_btn("👥 Foydalanuvchilar", "adm:users:0")],
            [_btn("📢 Majburiy obuna kanallari", "adm:channels")],
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
