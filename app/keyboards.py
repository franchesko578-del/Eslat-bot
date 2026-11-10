"""Tugmalar: reply va inline klaviaturalar. Hamma tugma rangli.

Ranglar (Telegram `style`): primary = ko'k, success = yashil, danger = qizil.
Eski Telegram ilovalari rangni ko'rsatmaydi, lekin tugma baribir ishlaydi.
"""
from typing import Optional

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.db import parse_ts
from app.emoji import (
    BACK,
    BELL,
    CAL,
    CHART,
    CROSS,
    DAYS,
    GEAR,
    GIFT,
    HOURGLASS,
    INFO,
    LIST,
    MEGA,
    MONTH,
    NEXT,
    NUMS,
    OK,
    PEOPLE,
    PENCIL,
    PLUS,
    REPEAT,
    SEND,
    SPARK,
    STATS,
    SUN,
    TRASH,
    USER,
)
from app.utils import DAY_NAMES, fmt_dt, short

BLUE = "primary"
GREEN = "success"
RED = "danger"

BTN_CREATE = f"{PLUS} Eslatma yaratish"
BTN_LIST = f"{LIST} Eslatmalarim"
BTN_RECURRING = f"{REPEAT} Takroriy eslatma"
BTN_SETTINGS = f"{GEAR} Sozlamalar"
BTN_FRIEND = f"{PEOPLE} Do'stga eslatma"
BTN_INVITE = f"{GIFT} Do'st taklif qilish"
BTN_CANCEL = f"{CROSS} Bekor qilish"


def btn(text: str, data: str, style: Optional[str] = BLUE) -> InlineKeyboardButton:
    extra = {"style": style} if style else {}
    return InlineKeyboardButton(text=text, callback_data=data, **extra)


def url_btn(text: str, url: str, style: Optional[str] = GREEN) -> InlineKeyboardButton:
    extra = {"style": style} if style else {}
    return InlineKeyboardButton(text=text, url=url, **extra)


def reply_btn(text: str, style: Optional[str] = BLUE, **kwargs) -> KeyboardButton:
    extra = {"style": style} if style else {}
    return KeyboardButton(text=text, **extra, **kwargs)


def _kb(rows: list) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- Asosiy menyu ----------
def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [reply_btn(BTN_CREATE, GREEN), reply_btn(BTN_LIST, BLUE)],
            [reply_btn(BTN_RECURRING, BLUE), reply_btn(BTN_FRIEND, BLUE)],
            [reply_btn(BTN_INVITE, GREEN), reply_btn(BTN_SETTINGS, BLUE)],
        ],
        resize_keyboard=True,
    )


def cancel_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[reply_btn(BTN_CANCEL, RED)]],
        resize_keyboard=True,
    )


# ---------- Yaratish ----------
def repeat_kb(recurring_only: bool) -> InlineKeyboardMarkup:
    rows = []
    if recurring_only:
        rows.append([btn(f"{REPEAT} Har kuni", "rep:daily", GREEN)])
    else:
        rows.append(
            [
                btn("1\ufe0f\u20e3 Bir marta", "rep:once", BLUE),
                btn(f"{REPEAT} Har kuni", "rep:daily", GREEN),
            ]
        )
    rows.append(
        [
            btn(f"{DAYS} Hafta kunlari", "rep:weekdays", BLUE),
            btn(f"{CAL} Har hafta", "rep:weekly", GREEN),
        ]
    )
    rows.append(
        [
            btn(f"{MONTH} Har oy", "rep:monthly", BLUE),
            btn(f"{NUMS} Har N kunda", "rep:interval", GREEN),
        ]
    )
    if not recurring_only:
        rows.append([btn(f"{SPARK} Maxsus sana va vaqt", "rep:custom", BLUE)])
    return _kb(rows)


def weekdays_kb(selected: list) -> InlineKeyboardMarkup:
    """Hafta kunlarini tanlash. Tanlanganlari yashil va belgili."""
    buttons = []
    for index, name in enumerate(DAY_NAMES):
        on = index in selected
        buttons.append(
            btn(f"{OK} {name}" if on else name, f"wd:{index}", GREEN if on else BLUE)
        )
    return _kb([buttons[:4], buttons[4:], [btn(f"{OK} Tayyor", "wd:ok", GREEN)]])


def every_kb() -> InlineKeyboardMarkup:
    values = (2, 3, 4, 5, 7, 10, 14, 30)
    buttons = [btn(f"{n} kun", f"ev:{n}", BLUE if i % 2 == 0 else GREEN)
               for i, n in enumerate(values)]
    return _kb([buttons[:4], buttons[4:]])


def date_kb(today_str: str, tomorrow_str: str) -> InlineKeyboardMarkup:
    return _kb(
        [
            [
                btn(f"{CAL} Bugun ({today_str})", "date:today", GREEN),
                btn(f"{CAL} Ertaga ({tomorrow_str})", "date:tomorrow", BLUE),
            ]
        ]
    )


def hour_kb() -> InlineKeyboardMarkup:
    """Soat: 00 dan 23 gacha."""
    buttons = [btn(f"{h:02d}", f"th:{h}") for h in range(24)]
    return _kb([buttons[i : i + 6] for i in range(0, 24, 6)])


def minute_kb() -> InlineKeyboardMarkup:
    """Minut: 00 dan 59 gacha."""
    buttons = [btn(f"{m:02d}", f"tm:{m}") for m in range(60)]
    rows = [buttons[i : i + 6] for i in range(0, 60, 6)]
    rows.append([btn(f"{BACK} Soatni o'zgartirish", "tb:hour", RED)])
    return _kb(rows)


# ---------- Eslatma kelganda ----------
def reminder_kb(reminder_id: int) -> InlineKeyboardMarkup:
    rid = reminder_id
    return _kb(
        [
            [
                btn(f"{BELL} 5 min", f"rm:snz:{rid}:5"),
                btn(f"{BELL} 10 min", f"rm:snz:{rid}:10"),
                btn(f"{BELL} 15 min", f"rm:snz:{rid}:15"),
            ],
            [
                btn(f"{HOURGLASS} 1 soat", f"rm:snz:{rid}:60"),
                btn(f"{SUN} Ertaga", f"rm:tom:{rid}"),
            ],
            [btn(f"{OK} Bajarildi", f"rm:done:{rid}", GREEN)],
        ]
    )


def quick_saved_kb(reminder_id: int) -> InlineKeyboardMarkup:
    return _kb(
        [
            [
                btn(f"{TRASH} Bekor qilish", f"q:del:{reminder_id}", RED),
                btn(f"{PEOPLE} Do'stga yuborish", f"fr:share:{reminder_id}", BLUE),
            ]
        ]
    )


def quick_ask_kb() -> InlineKeyboardMarkup:
    return _kb(
        [
            [
                btn(f"{BELL} Eslatma qilish", "q:ask", GREEN),
                btn(f"{CROSS} Yo'q", "q:no", RED),
            ]
        ]
    )


def share_kb(url: str, label: str = "Do'stga yuborish") -> InlineKeyboardMarkup:
    return _kb([[url_btn(f"{SEND} {label}", url, GREEN)]])


def subscribe_kb(channels: list) -> InlineKeyboardMarkup:
    """Majburiy obuna: har kanal uchun tugma va "Tekshirish"."""
    rows = []
    for channel in channels:
        url = channel_url(channel)
        if url:
            rows.append([url_btn(f"\U0001F4E2 {channel['title']}", url, BLUE)])
    rows.append([btn(f"{OK} Obuna bo'ldim, tekshirish", "sub:check", GREEN)])
    return _kb(rows)


def channel_url(channel: dict) -> Optional[str]:
    link = (channel.get("invite_link") or "").strip()
    if link.startswith("http"):
        return link
    chat_id = str(channel.get("chat_id") or "")
    if chat_id.startswith("@"):
        return f"https://t.me/{chat_id[1:]}"
    return None


# ---------- Eslatmalarim ----------
def list_kb(rows: list, page: int, total: int, page_size: int, tz):
    keyboard = []
    start = page * page_size
    for index, row in enumerate(rows, start=start + 1):
        when = fmt_dt(parse_ts(row["remind_at"]), tz)
        label = f"{index}. {when} {short(row['text'], 22)}"
        keyboard.append([btn(label, f"r:view:{row['id']}:{page}")])
    nav = []
    if page > 0:
        nav.append(btn(f"{BACK} Oldingi", f"list:{page - 1}"))
    if start + page_size < total:
        nav.append(btn(f"Keyingi {NEXT}", f"list:{page + 1}", GREEN))
    if nav:
        keyboard.append(nav)
    return _kb(keyboard)


def detail_kb(reminder_id: int, page: int) -> InlineKeyboardMarkup:
    return _kb(
        [
            [
                btn(f"{PENCIL} Matn", f"r:et:{reminder_id}:{page}", BLUE),
                btn(f"{PENCIL} Vaqt", f"r:ed:{reminder_id}:{page}", GREEN),
            ],
            [btn(f"{TRASH} O'chirish", f"r:del:{reminder_id}:{page}", RED)],
            [btn(f"{BACK} Orqaga", f"list:{page}", BLUE)],
        ]
    )


def confirm_delete_kb(reminder_id: int, page: int) -> InlineKeyboardMarkup:
    return _kb(
        [
            [
                btn(f"{TRASH} Ha, o'chirish", f"r:delyes:{reminder_id}:{page}", RED),
                btn(f"{BACK} Yo'q", f"r:view:{reminder_id}:{page}", GREEN),
            ]
        ]
    )


# ---------- Sozlamalar ----------
def pre_label(minutes: int) -> str:
    if not minutes:
        return "o'chiq"
    return "1 soat" if minutes == 60 else f"{minutes} daqiqa"


def settings_kb(is_admin: bool, pre: int = 0):
    rows = [
        [btn(f"{HOURGLASS} Oldindan ogohlantirish: {pre_label(pre)}", "set:pre", GREEN)],
        [btn(f"{INFO} Yordam", "set:help")],
        [btn(f"{TRASH} Barcha eslatmalarni o'chirish", "set:delall", RED)],
    ]
    if is_admin:
        rows.append([btn(f"{USER} Admin panel", "adm:open", GREEN)])
    return _kb(rows)


def pre_kb(current: int) -> InlineKeyboardMarkup:
    options = (0, 5, 10, 15, 30, 60)
    buttons = [
        btn(
            (f"{OK} " if n == current else "") + pre_label(n).capitalize(),
            f"pre:{n}",
            GREEN if n == current else BLUE,
        )
        for n in options
    ]
    return _kb([buttons[:3], buttons[3:], [btn(f"{BACK} Orqaga", "set:cancel", RED)]])


def confirm_delall_kb() -> InlineKeyboardMarkup:
    return _kb(
        [
            [
                btn(f"{TRASH} Ha, hammasini", "set:delall_yes", RED),
                btn(f"{BACK} Yo'q", "set:cancel", GREEN),
            ]
        ]
    )


# ---------- Admin ----------
def admin_kb() -> InlineKeyboardMarkup:
    return _kb(
        [
            [btn(f"{STATS} Statistika", "adm:stats", BLUE)],
            [btn(f"{CHART} Kunlik faollik", "adm:daily", GREEN)],
            [btn(f"{PEOPLE} Foydalanuvchilar", "adm:users:0", BLUE)],
            [btn(f"{MEGA} Majburiy obuna kanallari", "adm:channels", GREEN)],
            [btn(f"{MEGA} Hammaga xabar yuborish", "adm:broadcast", BLUE)],
        ]
    )


def broadcast_confirm_kb() -> InlineKeyboardMarkup:
    return _kb(
        [
            [
                btn(f"{OK} Yuborish", "bc:yes", GREEN),
                btn(f"{CROSS} Bekor qilish", "bc:no", RED),
            ]
        ]
    )
