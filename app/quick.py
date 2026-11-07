"""Tez yozish: "ertaga 9:00 dori ichish" kabi bitta xabarni tahlil qiladi.

Qo'llab-quvvatlanadi:
  Sana:    bugun, ertaga, indinga, dushanba..yakshanba, 2026-11-20,
           20.11.2026, 20 noyabr
  Vaqt:    9:00, 9.30, 9 00, 9, soat 9, 9 da, 0930
  Nisbiy:  30 daqiqadan keyin, 2 soatdan keyin, 1 soat 30 daqiqadan keyin,
           yarim soatdan keyin, 3 kundan keyin
  Takror:  har kuni, har hafta, har dushanba, har dushanba va juma,
           ish kunlari, har oy, har 3 kunda
  Kun payti: ertalab, tushda, kechqurun, kechasi (8 -> 20:00 kabi)
"""
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

MASK = "\x00"

WEEKDAYS = {
    "dushanba": 0,
    "seshanba": 1,
    "chorshanba": 2,
    "payshanba": 3,
    "juma": 4,
    "shanba": 5,
    "yakshanba": 6,
}
MONTHS = {
    "yanvar": 1, "fevral": 2, "mart": 3, "aprel": 4, "may": 5, "iyun": 6,
    "iyul": 7, "avgust": 8, "sentabr": 9, "sentyabr": 9, "oktabr": 10,
    "oktyabr": 10, "noyabr": 11, "dekabr": 12,
}
NUMBER_WORDS = {
    "bir": 1, "ikki": 2, "uch": 3, "to'rt": 4, "besh": 5, "olti": 6,
    "yetti": 7, "sakkiz": 8, "to'qqiz": 9, "o'n": 10,
}
PERIODS = {
    "ertalab": "morning", "ertalabki": "morning", "tongda": "morning",
    "tushda": "day", "tushlikda": "day", "kunduzi": "day", "kunduz": "day",
    "kechqurun": "evening", "kechki": "evening",
    "kechasi": "night", "tunda": "night",
}
# Soatdan keyin kelsa, raqam vaqt emas, miqdor ekanini bildiradi
NOT_TIME_WORDS = {
    "ta", "tadan", "dona", "donadan", "kg", "kilo", "kilogramm", "gramm",
    "gr", "g", "litr", "l", "ml", "so'm", "som", "sum", "ming", "million",
    "mln", "mlrd", "sm", "metr", "m", "marta", "martadan", "kishi", "nafar",
    "foiz", "usd", "dollar", "yosh", "yoshda", "kun", "kundan", "soat",
    "soatdan", "daqiqa", "daqiqadan", "min", "hafta", "haftadan", "oy",
    "oydan", "yil", "yildan", "tup", "bosh", "quti", "paket", "shisha",
    "stakan", "piyola", "xona", "savol", "bet", "bob", "raqam",
    "%", "$",
}
LEADING_TRASH = {"da", "ga", "dan", "soat", "va", "bilan"}
EDGE_COMMANDS = (
    r"eslatib\s+qo'y(?:ing|gin|ib)?",
    r"eslatgin",
    r"eslating",
    r"eslat",
    r"eslatma",
)

_WD = "|".join(WEEKDAYS)
_MN = "|".join(sorted(MONTHS, key=len, reverse=True))
_NW = "|".join(sorted(NUMBER_WORDS, key=len, reverse=True))
_UNIT = r"(?:soat|daqiqa|daq|minut|min|kun|hafta)"
_AMT = rf"(?:\d+|yarim|{_NW})"


@dataclass
class Quick:
    text: str = ""
    day: Optional[date] = None
    at: Optional[time] = None
    moment: Optional[datetime] = None  # UTC; to'liq vaqt topilgan bo'lsa
    repeat: Optional[str] = None  # daily/weekly/weekdays/monthly/interval
    days: Optional[list] = None  # weekdays uchun: [0, 2, 4]
    every: Optional[int] = None  # interval uchun: N kun
    error: Optional[str] = None
    found: bool = False  # sana, vaqt yoki takror topildimi


def normalize(text: str) -> str:
    table = {ord(c): "'" for c in "\u02bb\u02bc\u2019\u2018`\u00b4"}
    return text.translate(table)


def _mask(work: str, m: "re.Match") -> str:
    return work[: m.start()] + MASK * (m.end() - m.start()) + work[m.end():]


def _next_word(work: str, pos: int) -> str:
    m = re.match(r"\s*([^\s\x00]+)", work[pos:])
    return m.group(1).lower().strip(".,;:!?") if m else ""


def _num(token: str) -> float:
    token = token.lower()
    if token == "yarim":
        return 0.5
    if token in NUMBER_WORDS:
        return float(NUMBER_WORDS[token])
    return float(token)


def _adjust_hour(hour: int, period: Optional[str]) -> int:
    if period == "day" and 1 <= hour <= 6:
        return hour + 12
    if period == "evening" and 1 <= hour <= 11:
        return hour + 12
    if period == "night":
        if 6 <= hour <= 11:
            return hour + 12
        if hour == 12:
            return 0
    return hour


def _first_weekday(start: date, at: time, days: list, now: datetime, tz: ZoneInfo):
    for i in range(0, 15):
        d = start + timedelta(days=i)
        if d.weekday() in days:
            cand = datetime.combine(d, at, tzinfo=tz)
            if cand > now:
                return d, cand.astimezone(timezone.utc)
    return None, None


def _local(d: date, t: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(d, t, tzinfo=tz).astimezone(timezone.utc)


def parse_quick(raw: str, now: datetime, tz: ZoneInfo) -> Quick:
    """`now` - hozirgi mahalliy vaqt (tz bilan). Natija: Quick."""
    s = normalize(raw)
    work = s
    res = Quick()
    today = now.date()

    day: Optional[date] = None
    day_explicit_today = False
    day_is_fixed_date = False
    repeat: Optional[str] = None
    at: Optional[time] = None
    period: Optional[str] = None
    rel_minutes: Optional[float] = None
    rel_only_days = False
    weekday: Optional[int] = None

    flags = re.I

    # ---- 1. Takrorlanish ----
    rep_days: Optional[list] = None
    rep_every: Optional[int] = None
    m = re.search(
        rf"\bhar\s+((?:{_WD})\w*(?:\s*(?:,|va)\s*(?:{_WD})\w*)*)(?:\s+kuni)?",
        work,
        flags,
    )
    if m:
        names = re.findall(rf"\b({_WD})", m.group(1), flags)
        found_days = sorted({WEEKDAYS[n.lower()] for n in names})
        if len(found_days) > 1:
            repeat = "weekdays"
            rep_days = found_days
        elif found_days:
            repeat = "weekly"
            weekday = found_days[0]
        work = _mask(work, m)
    m = re.search(r"\b(?:har\s+)?ish\s+kun(?:i|lari)\b", work, flags)
    if m and repeat is None:
        repeat = "weekdays"
        rep_days = [0, 1, 2, 3, 4]
        work = _mask(work, m)
    m = re.search(r"\bhar\s+(\d{1,3})\s*kun\w*", work, flags)
    if m and repeat is None:
        n = int(m.group(1))
        if n == 1:
            repeat = "daily"
        elif 2 <= n <= 365:
            repeat = "interval"
            rep_every = n
        work = _mask(work, m)
    m = re.search(r"\bhar\s*hafta\w*|\bhaftalik\b", work, flags)
    if m and repeat is None:
        repeat = "weekly"
        work = _mask(work, m)
    m = re.search(r"\bhar\s*oy\w*|\boylik\b", work, flags)
    if m and repeat is None:
        repeat = "monthly"
        work = _mask(work, m)
    m = re.search(r"\bhar\s*kun(?:i|lari)?\b|\bkundalik\b", work, flags)
    if m and repeat is None:
        repeat = "daily"
        work = _mask(work, m)

    # ---- 2. "ertadan keyin" = indinga ----
    m = re.search(r"\bertadan\s+keyin\b", work, flags)
    if m:
        day = today + timedelta(days=2)
        work = _mask(work, m)

    # ---- 3. Nisbiy vaqt: "30 daqiqadan keyin" ----
    m = re.search(
        rf"((?:{_AMT}\s*{_UNIT}\w*\s*){{1,3}})\s*(?:keyin|so'ng|sonra)\b",
        work,
        flags,
    )
    if m:
        total = 0.0
        days_only = True
        for part in re.finditer(rf"({_AMT})\s*({_UNIT})", m.group(1), flags):
            value = _num(part.group(1))
            unit = part.group(2).lower()
            if unit.startswith("soat"):
                total += value * 60
                days_only = False
            elif unit.startswith(("daq", "min")):
                total += value
                days_only = False
            elif unit.startswith("kun"):
                total += value * 1440
            else:  # hafta
                total += value * 10080
        if total > 0:
            rel_minutes = total
            rel_only_days = days_only
            work = _mask(work, m)

    # ---- 4. Sana ----
    m = re.search(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)", work)
    if m:
        try:
            day = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            day_is_fixed_date = True
            work = _mask(work, m)
        except ValueError:
            res.error = "Sana noto'g'ri."
    if day is None:
        m = re.search(r"(?<![\d.])(\d{1,2})\.(\d{1,2})\.(\d{4})(?![\d.])", work)
        if m:
            try:
                day = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                day_is_fixed_date = True
                work = _mask(work, m)
            except ValueError:
                res.error = "Sana noto'g'ri."
    if day is None:
        m = re.search(
            rf"(?<!\d)(\d{{1,2}})\s*-?\s*({_MN})(?:da|dan|ga|gacha)?\b",
            work,
            flags,
        )
        if m:
            month = MONTHS[m.group(2).lower()]
            try:
                cand = date(today.year, month, int(m.group(1)))
                if cand < today:
                    cand = date(today.year + 1, month, int(m.group(1)))
                day = cand
                day_is_fixed_date = True
                work = _mask(work, m)
            except ValueError:
                res.error = "Sana noto'g'ri."
    if day is None:
        m = re.search(r"\bbugun\w*", work, flags)
        if m:
            day = today
            day_explicit_today = True
            work = _mask(work, m)
    if day is None:
        m = re.search(r"\bertaga\w*", work, flags)
        if m:
            day = today + timedelta(days=1)
            work = _mask(work, m)
    if day is None:
        m = re.search(r"\bindin\w*", work, flags)
        if m:
            day = today + timedelta(days=2)
            work = _mask(work, m)
    if day is None and weekday is None:
        m = re.search(
            rf"(?:\b(?:keyingi|kelasi)\s+)?\b({_WD})\w*(?:\s+kuni)?",
            work,
            flags,
        )
        if m:
            weekday = WEEKDAYS[m.group(1).lower()]
            work = _mask(work, m)

    # ---- 5. Kun payti ----
    m = re.search(rf"\b({'|'.join(PERIODS)})\b", work, flags)
    if m:
        period = PERIODS[m.group(1).lower()]
        work = _mask(work, m)

    context = MASK in work

    # ---- 6. Vaqt ----
    def edge(m_: "re.Match") -> bool:
        left = work[: m_.start()].strip()
        right = work[m_.end():].strip()
        return not left or not right

    def accept_hm(h: int, mi: int) -> None:
        nonlocal at
        at = time(_adjust_hour(h, period), mi)

    # 6a. 9:00 yoki 9.30 (ikki nuqta - aniq vaqt)
    m = re.search(
        r"(?:\bsoat\s*)?(?<![\d:.])([01]?\d|2[0-3])\s*:\s*([0-5]\d)(?![\d:])"
        r"(?:\s*(?:da|ga|larda|gacha)\b)?",
        work,
        flags,
    )
    if m:
        accept_hm(int(m.group(1)), int(m.group(2)))
        work = _mask(work, m)
    # 6b. 9.30 (nuqta: sana yoki o'nlik kasr bilan adashmasligi uchun)
    if at is None:
        m = re.search(
            r"(?:\bsoat\s*)?(?<![\d:.])([01]?\d|2[0-3])\.([0-5]\d)(?![\d.:])"
            r"(?:\s*(?:da|ga|larda|gacha)\b)?",
            work,
            flags,
        )
        if m and (context or "soat" in m.group(0).lower() or edge(m)):
            if _next_word(work, m.end()) not in NOT_TIME_WORDS:
                accept_hm(int(m.group(1)), int(m.group(2)))
                work = _mask(work, m)
    # 6c. soat 9 / soat 9 30
    if at is None:
        m = re.search(
            r"\bsoat\s*([01]?\d|2[0-3])(?:\s+([0-5]\d))?(?![\d:.])"
            r"(?:\s*(?:da|ga|larda|gacha)\b)?",
            work,
            flags,
        )
        if m:
            minute = int(m.group(2)) if m.group(2) else 0
            if m.group(2) and _next_word(work, m.end(2)) in NOT_TIME_WORDS:
                # "soat 9 30 ta ..." - 30 miqdor, vaqt emas
                m = re.search(r"\bsoat\s*([01]?\d|2[0-3])(?![\d:.])", work, flags)
                minute = 0
            if m:
                accept_hm(int(m.group(1)), minute)
                work = _mask(work, m)
    # 6d. 9 00 (bo'sh joy bilan)
    if at is None:
        m = re.search(
            r"(?<![\d:.])([01]?\d|2[0-3])\s+([0-5]\d)(?![\d:.])"
            r"(?:\s*(?:da|ga|larda|gacha)\b)?",
            work,
        )
        if m and (context or edge(m)):
            if _next_word(work, m.end(2)) not in NOT_TIME_WORDS:
                accept_hm(int(m.group(1)), int(m.group(2)))
                work = _mask(work, m)
    # 6e. 9 yoki 9 da (faqat aniq belgi bo'lsa)
    if at is None:
        for m in re.finditer(
            r"(?<![\d:.\-])(\d{1,2})(?![\d:.\-])(\s*(?:da|ga|larda|gacha)\b)?",
            work,
            flags,
        ):
            hour = int(m.group(1))
            if hour > 23:
                continue
            nxt = _next_word(work, m.end(1))
            if nxt in NOT_TIME_WORDS and not m.group(2):
                continue
            has_suffix = bool(m.group(2))
            left = work[: m.start()].rstrip(" ")
            right = work[m.end():].lstrip(" ")
            adjacent = left.endswith(MASK) or right.startswith(MASK)
            if has_suffix or (context and adjacent):
                accept_hm(hour, 0)
                work = _mask(work, m)
                break

    # ---- 7. Qolgan matn ----
    rest = "".join(
        " " if work[i] == MASK else ch for i, ch in enumerate(s)
    )
    rest = " ".join(rest.split()).strip(" ,;:-\u2013\u2014.")
    changed = True
    while rest and changed:
        changed = False
        first = rest.split(" ", 1)
        if first[0].lower() in LEADING_TRASH:
            rest = first[1] if len(first) > 1 else ""
            rest = rest.strip(" ,;:-\u2013\u2014.")
            changed = True
        for cmd in EDGE_COMMANDS:
            new = re.sub(rf"(?:^|\s){cmd}\s*[.!]*$", "", rest, flags=re.I)
            new = re.sub(rf"^{cmd}\s+", "", new, flags=re.I)
            if new != rest:
                rest = new.strip(" ,;:-\u2013\u2014.")
                changed = True
    res.text = rest

    found = bool(
        day or weekday is not None or at or rel_minutes or repeat
    )
    res.found = found
    res.repeat = repeat
    res.days = rep_days
    res.every = rep_every
    res.at = at
    if res.error:
        return res

    # ---- 8. Vaqtni hisoblash ----
    if rel_minutes is not None:
        if rel_only_days:
            base = today + timedelta(days=int(round(rel_minutes / 1440)))
            if at is not None:
                res.day = base
                moment = _local(base, at, tz)
            else:
                dt = (now + timedelta(minutes=rel_minutes)).replace(
                    second=0, microsecond=0
                )
                res.day = dt.date()
                res.at = dt.time()
                moment = dt.astimezone(timezone.utc)
        else:
            dt = (now + timedelta(minutes=rel_minutes)).replace(
                second=0, microsecond=0
            )
            if dt <= now:
                dt += timedelta(minutes=1)
            res.day = dt.date()
            res.at = dt.time()
            moment = dt.astimezone(timezone.utc)
        res.moment = moment
        return res

    if repeat == "weekdays" and rep_days:
        if at is None:
            d, _ = _first_weekday(today, time(0, 0), rep_days, now - timedelta(days=1), tz)
            res.day = d
            return res
        d, moment = _first_weekday(today, at, rep_days, now, tz)
        res.day = d
        res.moment = moment
        return res

    if weekday is not None and day is None:
        delta = (weekday - today.weekday()) % 7
        cand = today + timedelta(days=delta)
        if delta == 0:
            if at is None or datetime.combine(cand, at, tzinfo=tz) <= now:
                cand += timedelta(days=7)
        day = cand

    res.day = day
    if at is None:
        return res  # sana bor, vaqt yo'q: vaqtni tugma bilan so'raymiz

    if day is None:
        cand = today
        if datetime.combine(cand, at, tzinfo=tz) <= now:
            cand += timedelta(days=1)
        day = cand
        res.day = day

    moment = _local(day, at, tz)
    if moment <= now.astimezone(timezone.utc):
        if day_explicit_today:
            res.error = f"Bugun soat {at.strftime('%H:%M')} o'tib ketgan."
        elif day_is_fixed_date:
            res.error = "Bu sana va vaqt o'tib ketgan."
        else:
            res.error = "Bu vaqt o'tib ketgan."
        return res
    res.moment = moment
    return res
