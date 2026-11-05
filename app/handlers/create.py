"""Eslatma yaratish: matn -> takrorlanish -> sana -> vaqt (tugma yoki yozib)."""
from datetime import datetime, time, timedelta

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, User

from app.config import Settings
from app.db import Database, iso_z
from app.emoji import CAL, MEMO, OK, REPEAT, WARN
from app.keyboards import cancel_menu, date_kb, main_menu, repeat_kb, time_kb
from app.sharing import send_share_card
from app.states import CreateReminder
from app.utils import (
    PLAIN,
    esc,
    fmt_dt,
    local_to_utc,
    now_utc,
    parse_date,
    parse_datetime_line,
    parse_time,
    repeat_label,
    today_local,
)

router = Router(name="create")
router.message.filter(F.chat.type == "private")

MAX_TEXT = 1000
MAX_CUSTOM_LINES = 20


async def begin(
    message: Message,
    state: FSMContext,
    db: Database,
    settings: Settings,
    recurring_only: bool,
    friend: bool = False,
) -> None:
    await state.clear()
    active = await db.count_active(message.from_user.id)
    if active >= settings.max_reminders:
        await message.answer(
            f"{WARN} Faol eslatmalar soni chegaraga yetdi "
            f"({settings.max_reminders} ta). Avval keraksizlarini "
            "o'chiring.",
            reply_markup=main_menu(),
        )
        return
    await state.set_state(CreateReminder.text)
    await state.update_data(recurring_only=recurring_only, friend=friend)
    prompt = (
        f"{MEMO} Do'stingiz uchun eslatma matnini yozing:"
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
            f"{WARN} Matn juda uzun ({len(text)} belgi). "
            f"Eng ko'pi {MAX_TEXT} belgi bo'lishi mumkin. Qisqaroq yozing."
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
        f"{REPEAT} Takrorlanish turini tanlang:",
        reply_markup=repeat_kb(bool(data.get("recurring_only"))),
    )


@router.callback_query(CreateReminder.repeat, F.data.startswith("rep:"))
async def got_repeat(
    call: CallbackQuery, state: FSMContext, settings: Settings
) -> None:
    await call.answer()
    kind = call.data.split(":", 1)[1]
    if kind not in ("once", "daily", "weekly", "custom"):
        return
    await state.update_data(repeat=kind)

    if kind == "custom":
        await state.set_state(CreateReminder.custom)
        label = "Maxsus sana va vaqt"
    else:
        await state.set_state(CreateReminder.date)
        label = repeat_label(kind)

    try:
        await call.message.edit_text(f"{REPEAT} Takrorlanish: <b>{label}</b>")
    except Exception:
        pass

    if kind == "custom":
        tomorrow = today_local(settings.tz) + timedelta(days=1)
        await call.message.answer(
            f"{CAL} Sana va vaqtlarni yozing. Har bir qatorga bittadan:\n\n"
            f"<code>{tomorrow.isoformat()} 09:00\n"
            f"{tomorrow.isoformat()} 18:30</code>\n\n"
            f"Format: YYYY-MM-DD HH:MM (eng ko'pi {MAX_CUSTOM_LINES} qator). "
            "Har bir qator uchun alohida eslatma yaratiladi."
        )
    else:
        await prompt_date(call.message, settings, kind)


async def prompt_date(target: Message, settings: Settings, kind: str) -> None:
    today = today_local(settings.tz)
    tomorrow = today + timedelta(days=1)
    extra = ""
    if kind != "once":
        extra = " (takrorlanish shu sanadan boshlanadi)"
    await target.answer(
        f"{CAL} Sanani <code>YYYY-MM-DD</code> ko'rinishida yozing"
        f"{extra}.\nMasalan: <code>{tomorrow.isoformat()}</code>\n\n"
        "Yoki quyidagi tugmalardan birini tanlang:",
        reply_markup=date_kb(today.isoformat(), tomorrow.isoformat()),
    )


async def ask_time(
    target: Message, state: FSMContext, chosen, settings: Settings
) -> None:
    """Vaqtni so'raydi: tayyor tugmalar yoki yozib (9, 9 00, 9:30)."""
    await state.update_data(date=chosen.isoformat())
    await state.set_state(CreateReminder.time)
    keyboard = time_kb(chosen, datetime.now(settings.tz))
    hint = (
        "Vaqtni tugmadan tanlang yoki yozing: <code>9</code>, "
        "<code>9 00</code>, <code>9:30</code> (24 soatlik)."
        if keyboard
        else "Vaqtni yozing: <code>9</code>, <code>9 00</code> yoki "
        "<code>21:30</code> (24 soatlik)."
    )
    await target.answer(
        f"Sana: <b>{chosen.isoformat()}</b>\n\n{hint}", reply_markup=keyboard
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
            f"{WARN} Sana noto'g'ri. <code>YYYY-MM-DD</code> ko'rinishida "
            "yozing. Masalan: <code>2026-11-05</code>"
        )
        return
    if chosen < today_local(settings.tz):
        await message.answer(
            f"{WARN} Bu sana o'tib ketgan. Bugungi yoki keyingi sanani yozing."
        )
        return
    await ask_time(message, state, chosen, settings)


async def finish_single(
    target: Message,
    user: User,
    state: FSMContext,
    bot: Bot,
    db: Database,
    settings: Settings,
    chosen_time: time,
) -> None:
    """Sana va vaqt tayyor: eslatmani (yoki do'st havolasini) yaratadi."""
    data = await state.get_data()
    chosen_date = parse_date(data["date"])
    remind_at = local_to_utc(chosen_date, chosen_time, settings.tz)
    if remind_at <= now_utc():
        await target.answer(
            f"{WARN} Bu vaqt o'tib ketgan. Kelajakdagi vaqtni tanlang yoki yozing."
        )
        return

    if data.get("friend"):
        await state.clear()
        await target.answer("Havola tayyorlanmoqda...", reply_markup=main_menu())
        await send_share_card(
            target, bot, db, settings, user, data["text"], remind_at
        )
        return

    if await db.count_active(user.id) >= settings.max_reminders:
        await state.clear()
        await target.answer(
            f"{WARN} Eslatmalar chegarasiga yetdingiz.",
            reply_markup=main_menu(),
        )
        return

    row = {
        "user_id": user.id,
        "text": data["text"],
        "remind_at": iso_z(remind_at),
        "repeat_type": data["repeat"],
    }
    await db.create_reminders([row])
    await state.clear()
    await target.answer(
        f"{OK} <b>Eslatma saqlandi!</b>\n\n"
        f"{MEMO} {esc(data['text'])}\n"
        f"{CAL} {fmt_dt(remind_at, settings.tz)}\n"
        f"{REPEAT} {repeat_label(data['repeat'])}",
        reply_markup=main_menu(),
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
            "<code>9 00</code>, <code>9:30</code> yoki <code>21:00</code>"
        )
        return
    await finish_single(
        message, message.from_user, state, bot, db, settings, chosen_time
    )


@router.callback_query(CreateReminder.time, F.data.startswith("tm:"))
async def got_time_button(
    call: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    db: Database,
    settings: Settings,
) -> None:
    chosen_time = parse_time(call.data[3:])
    if chosen_time is None:
        await call.answer()
        return
    await call.answer()
    try:
        await call.message.edit_text(f"Vaqt: <b>{chosen_time.strftime('%H:%M')}</b>")
    except Exception:
        pass
    await finish_single(
        call.message, call.from_user, state, bot, db, settings, chosen_time
    )


@router.message(CreateReminder.custom, PLAIN)
async def got_custom(
    message: Message, state: FSMContext, db: Database, settings: Settings
) -> None:
    lines = [line.strip() for line in message.text.splitlines() if line.strip()]
    if not lines or len(lines) > MAX_CUSTOM_LINES:
        await message.answer(
            f"{WARN} 1 tadan {MAX_CUSTOM_LINES} tagacha qator yozing."
        )
        return

    now = now_utc()
    parsed = []
    problems = []
    for number, line in enumerate(lines, start=1):
        moment = parse_datetime_line(line, settings.tz)
        if moment is None:
            problems.append(
                f"{number}-qator: format noto'g'ri (kerak: YYYY-MM-DD HH:MM)"
            )
        elif moment <= now:
            problems.append(f"{number}-qator: bu vaqt o'tib ketgan")
        else:
            parsed.append(moment)
    if problems:
        await message.answer(
            f"{WARN} Xatolar bor:\n" + "\n".join(problems) +
            "\n\nTuzatib, hammasini qayta yuboring."
        )
        return

    active = await db.count_active(message.from_user.id)
    if active + len(parsed) > settings.max_reminders:
        await message.answer(
            f"{WARN} Chegara: eng ko'pi {settings.max_reminders} ta faol "
            f"eslatma. Hozir {active} ta bor."
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
    when_list = "\n".join(
        f"{CAL} {fmt_dt(moment, settings.tz)}" for moment in sorted(parsed)
    )
    await message.answer(
        f"{OK} <b>{len(parsed)} ta eslatma saqlandi!</b>\n\n"
        f"{MEMO} {esc(data['text'])}\n\n{when_list}",
        reply_markup=main_menu(),
    )
