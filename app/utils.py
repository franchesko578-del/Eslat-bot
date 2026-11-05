"""Yordamchi funksiyalar: sana, vaqt va matn bilan ishlash."""
import html
import logging
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from aiogram import F
from aiogram.exceptions import TelegramBadRequest

from app.emoji import BOLT, CAL, CLOCK, PEOPLE, PENCIL, PLUS, REPEAT, WARN

logger = logging.getLogger(__name__)

UTC = timezone.utc
DT_FORMAT = "%Y-%m-%d %H:%M"

REPEAT_LABELS = {
    "once": "Bir marta",
    "daily": "Har kuni",
    "weekly": "Har hafta",
}

# Menyudagi tugmalarning oxirgi so'zlari (emoji o'zgarsa ham ishlaydi)
MENU_KEYWORDS = (
    "Eslatma yaratish",
    "Eslatmalarim",
    "Takroriy eslatma",
    "Do'stga eslatma",
    "Sozlamalar",
    "Bekor qilish",
)

HELP_TEXT = (
    f"{BOLT} <b>Tez yozish</b> - bitta xabar yozing, eslatma tayyor:\n"
    "<code>ertaga 9:00 dori ichish</code>\n"
    "<code>30 daqiqadan keyin choy</code>\n"
    "<code>har kuni 8 00 vitamin</code>\n"
    "<code>juma 18:00 futbol</code>\n"
    "Soatni <code>9</code>, <code>9 00</code>, <code>9:00</code> yoki "
    "<code>soat 9 da</code> deb yozsangiz ham bo'ladi.\n\n"
    f"{PLUS} <b>Eslatma yaratish</b> - matn, sana va vaqtni tugmalar bilan tanlaysiz.\n"
    f"{REPEAT} <b>Takroriy eslatma</b> - har kuni yoki har hafta.\n"
    f"{PEOPLE} <b>Do'stga eslatma</b> - havola orqali boshqa odamga eslatma yuborasiz.\n"
    f"{PENCIL} <b>Eslatmalarim</b> - ko'rish, tahrirlash, o'chirish.\n\n"
    f"{CAL} Sana: <code>YYYY-MM-DD</code> (masalan 2026-11-05)\n"
    f"{CLOCK} Vaqt: <code>09:30</code>, <code>9 30</code> yoki <code>9</code>\n"
    f"{WARN} Vaqt O'zbekiston vaqti (Asia/Tashkent) bo'yicha.\n\n"
    "Bekor qilish: /cancel"
)


def esc(text) -> str:
    """Foydalanuvchi matnini HTML uchun xavfsiz qiladi."""
    return html.escape(str(text), quote=False)


def short(text: str, limit: int = 40) -> str:
    """Matnni bir qatorga keltirib, kerak bo'lsa qisqartiradi."""
    flat = " ".join(str(text).split())
    if len(flat) > limit:
        return flat[: limit - 3] + "..."
    return flat


def is_menu_text(text: Optional[str]) -> bool:
    if not text:
        return False
    value = text.strip()
    if value.startswith("/"):
        return True
    return any(value.endswith(word) for word in MENU_KEYWORDS)


def is_plain_text(text: Optional[str]) -> bool:
    """Oddiy matnmi (menyu tugmasi yoki buyruq emasmi)."""
    return bool(text) and not is_menu_text(text)


# Holat ichida faqat oddiy matnni qabul qiluvchi filtr
PLAIN = F.text.func(is_plain_text)


def now_utc() -> datetime:
    return datetime.now(UTC)


def today_local(tz: ZoneInfo) -> date:
    return datetime.now(tz).date()


def start_of_today_utc(tz: ZoneInfo) -> datetime:
    midnight = datetime.combine(today_local(tz), time.min, tzinfo=tz)
    return midnight.astimezone(UTC)


def parse_date(text: str) -> Optional[date]:
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


_TIME_SPLIT = re.compile(r"^(\d{1,2})(?:\s*[:.\-]\s*|\s+)(\d{2})$")


def parse_time(text: str) -> Optional[time]:
    """Vaqtni erkin ko'rinishda o'qiydi: 9, 09, 9:00, 9.30, 9 00, 930, soat 9 da."""
    value = text.strip().lower().replace("soat", " ")
    value = re.sub(r"\s*(?:da|ga|larda|gacha)\s*$", "", value).strip()
    match = _TIME_SPLIT.match(value)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
    elif value.isdigit() and len(value) <= 2:
        hour, minute = int(value), 0
    elif value.isdigit() and len(value) in (3, 4):
        hour, minute = int(value[:-2]), int(value[-2:])
    else:
        return None
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return time(hour, minute)
    return None


def local_to_utc(d: date, t: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(d, t, tzinfo=tz).astimezone(UTC)


def parse_datetime_line(line: str, tz: ZoneInfo) -> Optional[datetime]:
    """'2026-11-05 09:30' ko'rinishidagi qatorni UTC vaqtga aylantiradi."""
    parts = line.replace("T", " ").split()
    if len(parts) < 2:
        return None
    d = parse_date(parts[0])
    t = parse_time(" ".join(parts[1:]))
    if d is None or t is None:
        return None
    return local_to_utc(d, t, tz)


def fmt_dt(dt: datetime, tz: ZoneInfo) -> str:
    return dt.astimezone(tz).strftime(DT_FORMAT)


def repeat_label(repeat_type: str) -> str:
    return REPEAT_LABELS.get(repeat_type, repeat_type)


def next_occurrence(
    remind_at: datetime, repeat_type: str, now: datetime
) -> Optional[datetime]:
    """Takroriy eslatmaning keyingi vaqti. Bir martalik bo'lsa None."""
    step = {"daily": timedelta(days=1), "weekly": timedelta(days=7)}.get(
        repeat_type
    )
    if step is None:
        return None
    nxt = remind_at + step
    if nxt <= now:
        # Server uxlab qolgan bo'lsa, o'tib ketganlarini o'tkazib yuboradi
        nxt = remind_at + step * ((now - remind_at) // step + 1)
    return nxt


async def safe_edit(call, text: str, reply_markup=None) -> None:
    """Xabarni tahrirlaydi; imkoni bo'lmasa yangi xabar yuboradi."""
    try:
        await call.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as error:
        if "not modified" in str(error).lower():
            return
        logger.warning("Xabarni tahrirlab bo'lmadi: %s", error)
        await call.message.answer(text, reply_markup=reply_markup)


