"""Eslatmalarim: ko'rish, tahrirlash va o'chirish."""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import Settings
from app.db import Database, iso_z, parse_ts
from app.emoji import CAL, LIST, MEMO, OK, PENCIL, REPEAT, WARN
from app.keyboards import (
    cancel_menu,
    confirm_delete_kb,
    detail_kb,
    list_kb,
    main_menu,
)
from app.states import EditReminder
from app.utils import (
    PLAIN,
    esc,
    fmt_dt,
    now_utc,
    parse_datetime_line,
    repeat_label,
    safe_edit,
    short,
)

router = Router(name="manage")
router.message.filter(F.chat.type == "private")

PAGE_SIZE = 5
MAX_TEXT = 1000


async def render_list(user_id: int, page: int, db: Database, settings: Settings):
    """Ro'yxat matni va tugmalarini tayyorlaydi."""
    rows, total = await db.list_active(user_id, page * PAGE_SIZE, PAGE_SIZE)
    if total == 0:
        return (
            "Hozircha faol eslatmalaringiz yo'q.\n\n"
            "Yangi eslatma yaratish uchun menyudan foydalaning.",
            None,
        )
    last_page = (total - 1) // PAGE_SIZE
    if page > last_page:
        page = last_page
        rows, total = await db.list_active(user_id, page * PAGE_SIZE, PAGE_SIZE)

    lines = [f"{LIST} <b>Eslatmalarim</b> ({total} ta)\n"]
    number = page * PAGE_SIZE + 1
    for row in rows:
        when = fmt_dt(parse_ts(row["remind_at"]), settings.tz)
        label = repeat_label(row["repeat_type"])
        lines.append(
            f"{number}. {CAL} {when} | {label}\n"
            f"    {esc(short(row['text'], 60))}"
        )
        number += 1
    lines.append("\nBatafsil ko'rish uchun tugmani bosing.")
    keyboard = list_kb(rows, page, total, PAGE_SIZE, settings.tz)
    return "\n".join(lines), keyboard


def detail_text(row: dict, settings: Settings) -> str:
    when = fmt_dt(parse_ts(row["remind_at"]), settings.tz)
    return (
        f"{MEMO} <b>Eslatma</b>\n\n{esc(row['text'])}\n\n"
        f"{CAL} {when}\n{REPEAT} {repeat_label(row['repeat_type'])}"
    )


@router.message(F.text.endswith("Eslatmalarim"))
async def menu_list(
    message: Message, state: FSMContext, db: Database, settings: Settings
) -> None:
    await state.clear()
    text, keyboard = await render_list(message.from_user.id, 0, db, settings)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("list:"))
async def cb_list(call: CallbackQuery, db: Database, settings: Settings) -> None:
    await call.answer()
    page = int(call.data.split(":")[1])
    text, keyboard = await render_list(call.from_user.id, page, db, settings)
    await safe_edit(call, text, keyboard)


async def _load(call: CallbackQuery, db: Database):
    """r:amal:id:sahifa ko'rinishidagi ma'lumotni o'qiydi."""
    parts = call.data.split(":")
    reminder_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 else 0
    row = await db.get_reminder(reminder_id, call.from_user.id)
    return reminder_id, page, row


async def _missing(call: CallbackQuery, db: Database, settings: Settings, page: int):
    await call.answer("Eslatma topilmadi (o'chirilgan bo'lishi mumkin).", show_alert=True)
    text, keyboard = await render_list(call.from_user.id, page, db, settings)
    await safe_edit(call, text, keyboard)


@router.callback_query(F.data.startswith("r:view:"))
async def cb_view(call: CallbackQuery, db: Database, settings: Settings) -> None:
    reminder_id, page, row = await _load(call, db)
    if row is None:
        await _missing(call, db, settings, page)
        return
    await call.answer()
    await safe_edit(call, detail_text(row, settings), detail_kb(reminder_id, page))


@router.callback_query(F.data.startswith("r:del:"))
async def cb_delete_ask(call: CallbackQuery, db: Database, settings: Settings) -> None:
    reminder_id, page, row = await _load(call, db)
    if row is None:
        await _missing(call, db, settings, page)
        return
    await call.answer()
    await safe_edit(
        call,
        f"{WARN} Shu eslatmani o'chirasizmi?\n\n{detail_text(row, settings)}",
        confirm_delete_kb(reminder_id, page),
    )


@router.callback_query(F.data.startswith("r:delyes:"))
async def cb_delete_yes(call: CallbackQuery, db: Database, settings: Settings) -> None:
    parts = call.data.split(":")
    reminder_id, page = int(parts[2]), int(parts[3])
    deleted = await db.delete_reminder(reminder_id, call.from_user.id)
    await call.answer(
        "O'chirildi" if deleted else "Eslatma topilmadi", show_alert=False
    )
    text, keyboard = await render_list(call.from_user.id, page, db, settings)
    await safe_edit(call, text, keyboard)


# ---------- Tahrirlash ----------
@router.callback_query(F.data.startswith("r:et:"))
async def cb_edit_text(
    call: CallbackQuery, state: FSMContext, db: Database, settings: Settings
) -> None:
    reminder_id, page, row = await _load(call, db)
    if row is None:
        await _missing(call, db, settings, page)
        return
    await call.answer()
    await state.set_state(EditReminder.text)
    await state.update_data(rid=reminder_id, page=page)
    await call.message.answer(
        f"{PENCIL} Yangi matnni yozing:", reply_markup=cancel_menu()
    )


@router.callback_query(F.data.startswith("r:ed:"))
async def cb_edit_when(
    call: CallbackQuery, state: FSMContext, db: Database, settings: Settings
) -> None:
    reminder_id, page, row = await _load(call, db)
    if row is None:
        await _missing(call, db, settings, page)
        return
    await call.answer()
    await state.set_state(EditReminder.when)
    await state.update_data(rid=reminder_id, page=page)
    await call.message.answer(
        f"{PENCIL} Yangi sana va vaqtni yozing:\n\n"
        "<code>YYYY-MM-DD HH:MM</code>\n"
        f"Masalan: <code>{fmt_dt(now_utc(), settings.tz)}</code> "
        "(kelajakdagi vaqt bo'lishi kerak)",
        reply_markup=cancel_menu(),
    )


async def _show_detail(message: Message, db: Database, settings: Settings, rid: int, page: int):
    row = await db.get_reminder(rid, message.from_user.id)
    if row is not None:
        await message.answer(
            detail_text(row, settings), reply_markup=detail_kb(rid, page)
        )


@router.message(EditReminder.text, PLAIN)
async def got_new_text(
    message: Message, state: FSMContext, db: Database, settings: Settings
) -> None:
    text = message.text.strip()
    if len(text) > MAX_TEXT:
        await message.answer(
            f"{WARN} Matn juda uzun. Eng ko'pi {MAX_TEXT} belgi."
        )
        return
    data = await state.get_data()
    updated = await db.update_reminder(data["rid"], message.from_user.id, {"text": text})
    await state.clear()
    if not updated:
        await message.answer("Eslatma topilmadi.", reply_markup=main_menu())
        return
    await message.answer(f"{OK} Matn yangilandi.", reply_markup=main_menu())
    await _show_detail(message, db, settings, data["rid"], data["page"])


@router.message(EditReminder.when, PLAIN)
async def got_new_when(
    message: Message, state: FSMContext, db: Database, settings: Settings
) -> None:
    moment = parse_datetime_line(message.text, settings.tz)
    if moment is None:
        await message.answer(
            f"{WARN} Format noto'g'ri. Kerak: <code>YYYY-MM-DD HH:MM</code>"
        )
        return
    if moment <= now_utc():
        await message.answer(f"{WARN} Bu vaqt o'tib ketgan.")
        return
    data = await state.get_data()
    fields = {"remind_at": iso_z(moment), "status": "active", "fail_count": 0}
    updated = await db.update_reminder(data["rid"], message.from_user.id, fields)
    await state.clear()
    if not updated:
        await message.answer("Eslatma topilmadi.", reply_markup=main_menu())
        return
    await message.answer(f"{OK} Vaqt yangilandi.", reply_markup=main_menu())
    await _show_detail(message, db, settings, data["rid"], data["page"])
