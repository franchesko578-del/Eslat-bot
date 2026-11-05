"""Ro'yxatdan o'tish (rozilik + telefon), yordam va bekor qilish."""
from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from app.config import Settings
from app.db import Database, is_registered
from app.emoji import BOLT, OK, WAVE
from app.keyboards import main_menu
from app.sharing import accept_gift, gift_token
from app.states import Registration
from app.utils import HELP_TEXT, esc

router = Router(name="start")
router.message.filter(F.chat.type == "private")

TERMS = (
    "<b>ESLATMA-BOT — FOYDALANISH SHARTLARI</b>\n\n"
    "Botdan foydalanishda firibgarlik va noqonuniy harakatlar taqiqlanadi. "
    "Ro'yxatdan o'tishda Telegram profilingiz va telefon raqamingiz qayta ishlanadi. "
    "Botga yuborgan xabarlaringiz xavfsizlik va xizmat faoliyatini ta'minlash "
    "maqsadida qayd etilishi mumkin. "
    "Ushbu ma'lumotlarni faqat vakolatli administrator ko'radi; ular qonuniy "
    "talablar asosida taqdim etilishi mumkin.\n\n"
    "Davom etish orqali ushbu shartlarga rozilik bildirasiz."
)

QUICK_HINT = (
    f"{BOLT} <b>Tez yozish:</b> shunchaki yozing, eslatma tayyor bo'ladi.\n"
    "<code>ertaga 9:00 dori ichish</code>\n"
    "<code>30 daqiqadan keyin choy</code>"
)


def terms_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Roziman va davom etaman", callback_data="reg:agree")]
        ]
    )


def phone_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Telefon raqamni ulashish", request_contact=True)]
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
        await message.answer(
            f"{WAVE} Salom, <b>{name}</b>!\n\n"
            f"Kerakli vaqtda sizga eslatma yuboraman.\n\n{QUICK_HINT}",
            reply_markup=main_menu(),
        )
        if token:
            await accept_gift(message, bot, db, settings, token)
        return
    if token:
        # Ro'yxatdan o'tgach, do'st eslatmasi avtomatik qabul qilinadi
        await state.update_data(gift=token)
    await message.answer(TERMS, reply_markup=terms_kb())


@router.callback_query(F.data == "reg:agree")
async def agree(call: CallbackQuery, state: FSMContext):
    await call.answer("Rozilik qabul qilindi")
    await state.set_state(Registration.phone)
    await call.message.answer(
        "Endi telefon raqamingizni Telegram tugmasi orqali yuboring:",
        reply_markup=phone_kb(),
    )


@router.message(Registration.phone, F.contact)
async def got_phone(
    message: Message, state: FSMContext, bot: Bot, db: Database, settings: Settings
):
    contact = message.contact
    if contact.user_id != message.from_user.id:
        await message.answer(
            "Iltimos, faqat o'zingizning telefon raqamingizni yuboring.",
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
    await message.answer(
        f"{OK} Ro'yxatdan o'tish yakunlandi. Botdan foydalanishingiz mumkin.\n\n"
        f"{QUICK_HINT}",
        reply_markup=main_menu(),
    )
    if token:
        await accept_gift(message, bot, db, settings, token)


@router.message(Registration.phone)
async def phone_required(message: Message):
    await message.answer(
        "Telefon raqamingizni pastdagi Telegram tugmasi orqali yuboring.",
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
            "Ro'yxatdan o'tish tugallanmagan. Botdan foydalanish uchun "
            "/start buyrug'i bilan qayta boshlang.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return
    await state.clear()
    await message.answer(f"{OK} Bekor qilindi.", reply_markup=main_menu())
