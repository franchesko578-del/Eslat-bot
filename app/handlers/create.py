"""Eslatma yaratish: matn -> takrorlash -> sana -> soat -> minut."""
from datetime import datetime, time, timedelta

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, User

from app.config import Settings
from app.db import Database, iso_z
from app.emoji import CAL, CLOCK, DAYS, MEMO, NUMS, OK, PEOPLE, REPEAT, WARN
from app.keyboards import (
    cancel_menu,
    date_kb,
    every_kb,
    hour_kb,
    main_menu,
    minute_kb,
    repeat_kb,
    weekdays_kb,
)
from app.sharing import send_share_card
from app.states import CreateReminder
from app.utils import (
    PLAIN,
    esc,
    first_weekday_occurrence,
    fmt_dt,
    format_days,
    local_to_utc,
    now_utc,
    parse_date,
    parse_datetime_line,
    parse_days,
    parse_time,
    repeat_extra,
    repeat_label,
    safe_edit,
    today_local,
)

router = Router(name="create")
router.message.filter(F.chat.type == "private")

MAX_TEXT = 1000
MAX_CUSTOM_LINES = 20
REPEAT_KINDS = {"once", "daily", "weekly", "weekdays", "monthly", "interval", "custom"}
DATE_HINTS = {
    "weekly": " (har hafta shu kunda)",
    "monthly": " (har oy shu sanada)",
    "interval": " (shu kundan boshlab)",
    "daily": " (shu kundan boshlab)",
}


async def begin(
    message: Message,
    state: FSMContext,
    db: Database,
    settings: Settings,
    recurring_only: bool,
    friend: bool = False,
) -> None:
    await state.clear()
    if await db.count_active(message.from_user.id) >= settings.max_reminders:
        await message.answer(
            f"{WARN} Eslatmalar chegarasiga yetdingiz ({settings.max_reminders} ta). "
            "Keraksizlarini o'chiring.",
            reply_markup=main_menu(),
        )
        return
    await state.set_state(CreateReminder.text)
    await state.update_data(recurring_only=recurring_only, friend=friend)
    prompt = (
        f"{PEOPLE} Do'stingiz uchun eslatma matnini yozing:"
        if friend
        else f"{MEMO} Eslatma matnini yozing:"
    )
    await message.answer(prompt, reply_markup=cancel_menu())


@router.message(F.text.endswith("Eslatma yaratish"))
async def menu_create(
    message: Message, state: FSMContext, db: Database, settings: Settings
) -> None:
    await begin(message, state, db, settings, False)


@router.message(F.text.endswith("Takroriy eslatma"))
async def menu_recurring(
    message: Message, state: FSMContext, db: Database, settings: Settings
) -> None:
    await begin(message, state, db, settings, True)


@router.message(CreateReminder.text, PLAIN)
async def got_text(
    message: Message, state: FSMContext, settings: Settings
) -> None:
    text = message.text.strip()
    if len(text) > MAX_TEXT:
        await message.answer(
            f"{WARN} Matn juda uzun ({len(text)} belgi). Eng ko'pi {MAX_TEXT}."
        )
        return
    data = await state.get_data()
    await state.update_data(text=text)
    if data.get("friend"):
        await state.update_data(repeat="once")
        await state.set_state(CreateReminder.date)
        await prompt_date(message, settings, "once")
        return
    await state.set_state(CreateReminder.repeat)
    await message.answer(
        f"{REPEAT} Qanday takrorlansin?",
        reply_markup=repeat_kb(bool(data.get("recurring_only"))),
    )


@router.callback_query(CreateReminder.repeat, F.data.startswith("rep:"))
async def got_repeat(
    call: CallbackQuery, state: FSMContext, settings: Settings
) -> None:
    await call.answer()
    kind = call.data.split(":", 1)[1]
    if kind not in REPEAT_KINDS:
        return
    await state.update_data(repeat=kind, days=[], every=None)

    if kind == "weekdays":
        await state.set_state(CreateReminder.days)
        await safe_edit(
            call,
            f"{DAYS} <b>Hafta kunlarini tanlang</b>\nBir nechtasini belgilab, "
            "\"Tayyor\" ni bosing:",
            weekdays_kb([]),
        )
        return
    if kind == "interval":
        await state.set_state(CreateReminder.every)
        await safe_edit(
            call,
            f"{NUMS} <b>Necha kunda bir marta?</b>\nTugmani bosing yoki raqam yozing:",
            every_kb(),
        )
        return
    if kind == "custom":
        await state.set_state(CreateReminder.custom)
        await safe_edit(call, f"{REPEAT} <b>Maxsus sana va vaqt</b>")
        tomorrow = today_local(settings.tz) + timedelta(days=1)
        await call.message.answer(
            f"{CAL} Har qatorga bittadan yozing:\n\n"
            f"<code>{tomorrow.isoformat()} 09:00\n"
            f"{tomorrow.isoformat()} 18:30</code>\n\n"
            f"Eng ko'pi {MAX_CUSTOM_LINES} qator. Har biriga alohida eslatma yaratiladi."
        )
        return
    await state.set_state(CreateReminder.date)
    await safe_edit(call, f"{REPEAT} <b>{repeat_label(kind)}</b>")
    await prompt_date(call.message, settings, kind)


# ---------- Hafta kunlari ----------
@router.callback_query(CreateReminder.days, F.data.startswith("wd:"))
async def got_weekday(
    call: CallbackQuery, state: FSMContext, settings: Settings
) -> None:
    arg = call.data[3:]
    data = await state.get_data()
    chosen = set(parse_days(data.get("days")))
    if arg == "ok":
        if not chosen:
            await call.answer("Kamida bitta kunni tanlang", show_alert=True)
            return
        await call.answer()
        days = sorted(chosen)
        await state.update_data(days=days)
        await safe_edit(
            call, f"{REPEAT} <b>{repeat_label('weekdays', format_days(days))}</b>"
        )
        await ask_time(call.message, state, today_local(settings.tz), settings)
        return
    if not arg.isdigit() or not 0 <= int(arg) <= 6:
        await call.answer()
        return
    chosen ^= {int(arg)}
    await state.update_data(days=sorted(chosen))
    await call.answer()
    try:
        await call.message.edit_reply_markup(reply_markup=weekdays_kb(sorted(chosen)))
    except Exception:
        pass


# ---------- Har N kunda ----------
async def _set_every(target: Message, state: FSMContext, settings: Settings, n: int):
    await state.update_data(every=n)
    await state.set_state(CreateReminder.date)
    await prompt_date(target, settings, "interval")


@router.callback_query(CreateReminder.every, F.data.startswith("ev:"))
async def got_every_button(
    call: CallbackQuery, state: FSMContext, settings: Settings
) -> None:
    await call.answer()
    n = int(call.data[3:])
    await safe_edit(call, f"{REPEAT} <b>{repeat_label('interval', every=n)}</b>")
    await _set_every(call.message, state, settings, n)


@router.message(CreateReminder.every, PLAIN)
async def got_every_text(
    message: Message, state: FSMContext, settings: Settings
) -> None:
    value = message.text.strip()
    if not value.isdigit() or not 2 <= int(value) <= 365:
        await message.answer(f"{WARN} 2 dan 365 gacha raqam yozing yoki tugmani bosing.")
        return
    await _set_every(message, state, settings, int(value))


# ---------- Sana ----------
async def prompt_date(target: Message, settings: Settings, kind: str) -> None:
    today = today_local(settings.tz)
    tomorrow = today + timedelta(days=1)
    await target.answer(
        f"{CAL} Sanani tanlang yoki yozing{DATE_HINTS.get(kind, '')}:\n"
        f"<code>{tomorrow.isoformat()}</code>",
        reply_markup=date_kb(today.isoformat(), tomorrow.isoformat()),
    )


@router.callback_query(CreateReminder.date, F.data.startswith("date:"))
async def got_date_button(
    call: CallbackQuery, state: FSMContext, settings: Settings
) -> None:
    await call.answer()
    today = today_local(settings.tz)
    which = call.data.split(":", 1)[1]
    chosen = today if which == "today" else today + timedelta(days=1)
    await ask_time(call.message, state, chosen, settings)


@router.message(CreateReminder.date, PLAIN)
async def got_date_text(
    message: Message, state: FSMContext, settings: Settings
) -> None:
    chosen = parse_date(message.text)
    if chosen is None:
        await message.answer(
            f"{WARN} Sana noto'g'ri. Masalan: <code>2026-11-05</code>"
        )
        return
    if chosen < today_local(settings.tz):
        await message.answer(f"{WARN} Bu sana o'tib ketgan.")
        return
    await ask_time(message, state, chosen, settings)


# ---------- Vaqt: soat va minut ----------
def _header(data: dict) -> str:
    lines = [f"{MEMO} {esc(data.get('text', ''))}"]
    repeat = data.get("repeat", "once")
    if repeat != "weekdays":
        lines.append(f"{CAL} {data.get('date', '')}")
    if repeat != "once":
        lines.append(
            f"{REPEAT} {repeat_label(repeat, format_days(data.get('days')), data.get('every'))}"
        )
    return "\n".join(lines)


async def ask_time(
    target: Message, state: FSMContext, chosen, settings: Settings
) -> None:
    """Avval soat (00-23), keyin minut (00-59) tugmalari."""
    await state.update_data(date=chosen.isoformat(), hour=None)
    await state.set_state(CreateReminder.time)
    data = await state.get_data()
    await target.answer(
        f"{_header(data)}\n\n{CLOCK} <b>Soatni tanlang</b> <i>(yoki yozing: 9:30)</i>",
        reply_markup=hour_kb(),
    )


def _is_weekdays(data: dict) -> bool:
    return data.get("repeat") == "weekdays"


@router.callback_query(CreateReminder.time, F.data.startswith("th:"))
async def got_hour(
    call: CallbackQuery, state: FSMContext, settings: Settings
) -> None:
    hour = int(call.data[3:])
    data = await state.get_data()
    now = datetime.now(settings.tz)
    if (
        not _is_weekdays(data)
        and parse_date(data["date"]) == now.date()
        and hour < now.hour
    ):
        await call.answer("Bu soat o'tib ketgan", show_alert=True)
        return
    await call.answer()
    await state.update_data(hour=hour)
    await safe_edit(
        call,
        f"{_header(data)}\n{CLOCK} Soat: <b>{hour:02d}</b>\n\n<b>Minutni tanlang</b>",
        minute_kb(),
    )


@router.callback_query(CreateReminder.time, F.data == "tb:hour")
async def back_to_hour(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    data = await state.get_data()
    await state.update_data(hour=None)
    await safe_edit(
        call,
        f"{_header(data)}\n\n{CLOCK} <b>Soatni tanlang</b> <i>(yoki yozing: 9:30)</i>",
        hour_kb(),
    )


def _remind_at(data: dict, chosen_time: time, settings: Settings):
    """Eslatmaning aniq vaqti (UTC). Hafta kunlari uchun birinchi mos kun."""
    chosen_date = parse_date(data["date"])
    if _is_weekdays(data):
        return first_weekday_occurrence(
            chosen_date, chosen_time, data.get("days"), now_utc(), settings.tz
        )
    return local_to_utc(chosen_date, chosen_time, settings.tz)


@router.callback_query(CreateReminder.time, F.data.startswith("tm:"))
async def got_minute(
    call: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    db: Database,
    settings: Settings,
) -> None:
    payload = call.data[3:]
    data = await state.get_data()
    if payload.isdigit():
        hour = data.get("hour")
        if hour is None:
            await call.answer("Avval soatni tanlang", show_alert=True)
            return
        chosen_time = time(int(hour), int(payload))
    else:  # eski xabarlardagi "tm:09:00" tugmalari
        chosen_time = parse_time(payload)
        if chosen_time is None:
            await call.answer()
            return
    remind_at = _remind_at(data, chosen_time, settings)
    if remind_at is None or remind_at <= now_utc():
        await call.answer("Bu vaqt o'tib ketgan. Boshqa minutni tanlang", show_alert=True)
        return
    await call.answer()
    try:
        await call.message.edit_text(
            f"{_header(data)}\n{CLOCK} Vaqt: <b>{chosen_time.strftime('%H:%M')}</b>"
        )
    except Exception:
        pass
    await finish_single(
        call.message, call.from_user, state, bot, db, settings, chosen_time
    )


@router.message(CreateReminder.time, PLAIN)
async def got_time(
    message: Message,
    state: FSMContext,
    bot: Bot,
    db: Database,
    settings: Settings,
) -> None:
    chosen_time = parse_time(message.text)
    if chosen_time is None:
        await message.answer(
            f"{WARN} Vaqt tushunarsiz. Masalan: <code>9</code>, "
            "<code>9 00</code>, <code>9:30</code>"
        )
        return
    await finish_single(
        message, message.from_user, state, bot, db, settings, chosen_time
    )


async def finish_single(
    target: Message,
    user: User,
    state: FSMContext,
    bot: Bot,
    db: Database,
    settings: Settings,
    chosen_time: time,
) -> None:
    """Hammasi tayyor: eslatmani (yoki do'st havolasini) yaratadi."""
    data = await state.get_data()
    repeat = data.get("repeat", "once")
    remind_at = _remind_at(data, chosen_time, settings)
    if remind_at is None or remind_at <= now_utc():
        await target.answer(f"{WARN} Bu vaqt o'tib ketgan. Kelajakdagi vaqtni tanlang.")
        return

    if data.get("friend"):
        await state.clear()
        await target.answer(f"{PEOPLE} Havola tayyorlanmoqda...", reply_markup=main_menu())
        await send_share_card(target, bot, db, settings, user, data["text"], remind_at)
        return

    if await db.count_active(user.id) >= settings.max_reminders:
        await state.clear()
        await target.answer(
            f"{WARN} Eslatmalar chegarasiga yetdingiz.", reply_markup=main_menu()
        )
        return

    start_day = remind_at.astimezone(settings.tz).date()
    row = {
        "user_id": user.id,
        "text": data["text"],
        "remind_at": iso_z(remind_at),
        "repeat_type": repeat,
        **repeat_extra(repeat, data.get("days"), data.get("every"), start_day),
    }
    await db.create_reminders([row])
    await state.clear()
    lines = [
        f"{OK} <b>Saqlandi</b>\n",
        f"{MEMO} {esc(data['text'])}",
        f"{CAL} {fmt_dt(remind_at, settings.tz)}",
    ]
    if repeat != "once":
        label = repeat_label(
            repeat, row.get("repeat_days"), row.get("repeat_every")
        )
        lines.append(f"{REPEAT} {label}")
    await target.answer("\n".join(lines), reply_markup=main_menu())


# ---------- Maxsus sana va vaqtlar ----------
@router.message(CreateReminder.custom, PLAIN)
async def got_custom(
    message: Message, state: FSMContext, db: Database, settings: Settings
) -> None:
    lines = [line.strip() for line in message.text.splitlines() if line.strip()]
    if not lines or len(lines) > MAX_CUSTOM_LINES:
        await message.answer(f"{WARN} 1 tadan {MAX_CUSTOM_LINES} tagacha qator yozing.")
        return

    now = now_utc()
    parsed = []
    problems = []
    for number, line in enumerate(lines, start=1):
        moment = parse_datetime_line(line, settings.tz)
        if moment is None:
            problems.append(f"{number}-qator: format noto'g'ri (YYYY-MM-DD 9:30)")
        elif moment <= now:
            problems.append(f"{number}-qator: bu vaqt o'tib ketgan")
        else:
            parsed.append(moment)
    if problems:
        await message.answer(
            f"{WARN} Xatolar:\n" + "\n".join(problems) + "\n\nTuzatib, qayta yuboring."
        )
        return

    active = await db.count_active(message.from_user.id)
    if active + len(parsed) > settings.max_reminders:
        await message.answer(
            f"{WARN} Chegara {settings.max_reminders} ta, hozir {active} ta bor."
        )
        return

    data = await state.get_data()
    rows = [
        {
            "user_id": message.from_user.id,
            "text": data["text"],
            "remind_at": iso_z(moment),
            "repeat_type": "once",
        }
        for moment in parsed
    ]
    await db.create_reminders(rows)
    await state.clear()
    when_list = "\n".join(f"{CAL} {fmt_dt(m, settings.tz)}" for m in sorted(parsed))
    await message.answer(
        f"{OK} <b>{len(parsed)} ta eslatma saqlandi</b>\n\n"
        f"{MEMO} {esc(data['text'])}\n{when_list}",
        reply_markup=main_menu(),
    )
