"""Ro'yxatdan o'tish (rozilik + telefon), yordam va bekor qilish."""
from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from app.config import Settings
from app.db import Database, is_registered
from app.emoji import OK, WAVE
from app.keyboards import GREEN, main_menu, reply_btn
from app.sharing import accept_gift, gift_token
from app.states import Registration
from app.utils import HELP_TEXT, esc

router = Router(name="start")
router.message.filter(F.chat.type == "private")

VERIFY_TEXT = "Akkauntingizni tasdiqlang \U0001F447"


def phone_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [reply_btn("📱 Telefon raqamni ulashish", GREEN, request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    bot: Bot,
    db: Database,
    settings: Settings,
    command: CommandObject,
) -> None:
    await state.clear()
    token = gift_token(command.args)
    user = await db.get_user(message.from_user.id)
    if is_registered(user):
        if user.get("is_blocked"):
            await message.answer(
                "Sizning botdan foydalanishingiz cheklangan. "
                "Savol bo'lsa administratorga murojaat qiling."
            )
            return
        name = esc(message.from_user.first_name or "foydalanuvchi")
        await message.answer(f"{WAVE} Salom, <b>{name}</b>!", reply_markup=main_menu())
        if token:
            await accept_gift(message, bot, db, settings, token)
        return
    if token:
        # Ro'yxatdan o'tgach, do'st eslatmasi avtomatik qabul qilinadi
        await state.update_data(gift=token)
    await state.set_state(Registration.phone)
    await message.answer(VERIFY_TEXT, reply_markup=phone_kb())


@router.callback_query(F.data == "reg:agree")
async def agree(call: CallbackQuery, state: FSMContext):
    """Eski xabarlardagi "Roziman" tugmasi uchun."""
    await call.answer()
    await state.set_state(Registration.phone)
    await call.message.answer(VERIFY_TEXT, reply_markup=phone_kb())


@router.message(Registration.phone, F.contact)
async def got_phone(
    message: Message, state: FSMContext, bot: Bot, db: Database, settings: Settings
):
    contact = message.contact
    if contact.user_id != message.from_user.id:
        await message.answer(
            "Faqat o'zingizning raqamingizni yuboring.",
            reply_markup=phone_kb(),
        )
        return
    await db.register_user(
        message.from_user.id,
        message.from_user.full_name,
        message.from_user.username,
        contact.phone_number,
    )
    data = await state.get_data()
    token = data.get("gift")
    await state.clear()
    await message.answer(f"{OK} Akkaunt tasdiqlandi.", reply_markup=main_menu())
    if token:
        await accept_gift(message, bot, db, settings, token)


@router.message(Registration.phone)
async def phone_required(message: Message):
    await message.answer(
        VERIFY_TEXT,
        reply_markup=phone_kb(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=main_menu())


@router.message(Command("cancel"))
@router.message(F.text.endswith("Bekor qilish"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current == Registration.phone.state:
        await message.answer(
            "Akkaunt tasdiqlanmadi. Qayta boshlash uchun /start bosing.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return
    await state.clear()
    await message.answer(f"{OK} Bekor qilindi.", reply_markup=main_menu())
