"""Yordamchi funksiyalar: sana, vaqt va matn bilan ishlash."""
import calendar
import html
import logging
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from aiogram import F
from aiogram.exceptions import TelegramBadRequest

from app.emoji import (
    BELL,
    BOLT,
    CAL,
    CLOCK,
    HOURGLASS,
    PEOPLE,
    PENCIL,
    PLUS,
    REPEAT,
    SUN,
    WARN,
)

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
    f"{BOLT} <b>Tez yozish</b>: bitta xabar, eslatma tayyor\n"
    "<code>ertaga 9:00 dori ichish</code>\n"
    "<code>30 daqiqadan keyin choy</code>\n"
    "<code>har kuni 8 00 vitamin</code>\n"
    "<code>har dushanba, juma 18:00 futbol</code>\n"
    "<code>har 3 kunda 9:00 dori</code>\n"
    "Soat: <code>9</code>, <code>9 00</code>, <code>9:30</code>, "
    "<code>soat 9 da</code>\n\n"
    f"{PLUS} <b>Eslatma yaratish</b>: matn, sana, soat va minut tugmalar bilan\n"
    f"{REPEAT} <b>Takroriy</b>: har kuni, hafta kunlari, har oy, har N kunda\n"
    f"{PEOPLE} <b>Do'stga eslatma</b>: havola orqali boshqaga yuborasiz\n"
    f"{PENCIL} <b>Eslatmalarim</b>: ko'rish, tahrirlash, o'chirish\n\n"
    f"{BELL} Eslatma kelganda: 5, 10, 15 daqiqa, 1 soat yoki ertaga qayta eslatish\n"
    f"{HOURGLASS} Sozlamalarda: oldindan ogohlantirish\n"
    f"{SUN} Sozlamalarda: ertalabki bugungi ro'yxat\n\n"
    f"{CLOCK} Vaqt O'zbekiston vaqti bo'yicha. Bekor qilish: /cancel"
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


DAY_NAMES = ["Du", "Se", "Chor", "Pay", "Ju", "Sha", "Yak"]


def parse_days(value) -> list:
    """'0,2,4' yoki [0, 2, 4] ni [0, 2, 4] ga aylantiradi (0 = dushanba)."""
    if not value:
        return []
    items = value if isinstance(value, (list, tuple, set)) else str(value).split(",")
    result = set()
    for item in items:
        item = str(item).strip()
        if item.isdigit() and 0 <= int(item) <= 6:
            result.add(int(item))
    return sorted(result)


def format_days(days) -> str:
    return ",".join(str(d) for d in parse_days(days))


def repeat_label(repeat_type: str, days=None, every=None) -> str:
    if repeat_type == "weekdays":
        chosen = parse_days(days)
        if chosen == [0, 1, 2, 3, 4]:
            return "Ish kunlari (Du-Ju)"
        names = ", ".join(DAY_NAMES[d] for d in chosen)
        return f"Har hafta: {names}" if names else "Hafta kunlari"
    if repeat_type == "monthly":
        return f"Har oy ({every}-sana)" if every else "Har oy"
    if repeat_type == "interval":
        return f"Har {every} kunda" if every else "Har N kunda"
    return REPEAT_LABELS.get(repeat_type, repeat_type)


def row_repeat(row: dict) -> str:
    return repeat_label(
        row.get("repeat_type", "once"), row.get("repeat_days"), row.get("repeat_every")
    )


def repeat_extra(repeat: str, days=None, every=None, start: Optional[date] = None) -> dict:
    """Takrorlash turiga qarab qo'shimcha ustunlar (repeat_days, repeat_every)."""
    if repeat == "weekdays":
        return {"repeat_days": format_days(days)}
    if repeat == "interval" and every:
        return {"repeat_every": int(every)}
    if repeat == "monthly":
        day = start.day if start else every
        return {"repeat_every": int(day)} if day else {}
    return {}


def first_weekday_occurrence(
    start: date, at: time, days, now: datetime, tz: ZoneInfo
) -> Optional[datetime]:
    """start sanasidan boshlab, tanlangan hafta kunlaridagi birinchi kelajak vaqt."""
    wanted = set(parse_days(days))
    if not wanted:
        return None
    for i in range(0, 15):
        d = start + timedelta(days=i)
        if d.weekday() in wanted:
            candidate = local_to_utc(d, at, tz)
            if candidate > now:
                return candidate
    return None


def next_occurrence(
    remind_at: datetime,
    repeat_type: str,
    now: datetime,
    tz: Optional[ZoneInfo] = None,
    days=None,
    every=None,
) -> Optional[datetime]:
    """Takroriy eslatmaning keyingi vaqti. Bir martalik bo'lsa None."""
    tz = tz or UTC
    if repeat_type in ("daily", "weekly", "interval"):
        n = {"daily": 1, "weekly": 7}.get(repeat_type) or max(1, int(every or 1))
        step = timedelta(days=n)
        nxt = remind_at + step
        if nxt <= now:
            # Server uxlab qolgan bo'lsa, o'tib ketganlarini o'tkazib yuboradi
            nxt = remind_at + step * ((now - remind_at) // step + 1)
        return nxt
    local = remind_at.astimezone(tz)
    at = local.time()
    if repeat_type == "weekdays":
        wanted = set(parse_days(days))
        if not wanted:
            return None
        d = local.date()
        for _ in range(3700):
            d += timedelta(days=1)
            if d.weekday() in wanted:
                candidate = local_to_utc(d, at, tz)
                if candidate > now:
                    return candidate
        return None
    if repeat_type == "monthly":
        day = int(every) if every else local.day
        year, month = local.year, local.month
        for _ in range(240):
            month += 1
            if month > 12:
                month, year = 1, year + 1
            last = calendar.monthrange(year, month)[1]
            candidate = local_to_utc(date(year, month, min(day, last)), at, tz)
            if candidate > now:
                return candidate
        return None
    return None


async def safe_edit(call, text: str, reply_markup=None) -> None:
    """Xabarni tahrirlaydi; imkoni bo'lmasa yangi xabar yuboradi."""
    try:
        await call.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as error:
        if "not modified" in str(error).lower():
            return
        logger.warning("Xabarni tahrirlab bo'lmadi: %s", error)
        await call.message.answer(text, reply_markup=reply_markup)


