"""Ro'yxatdan o'tish (telefon orqali tasdiqlash), start tushuntirishi va yordam."""
from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove

from app.config import Settings
from app.db import Database, is_registered
from app.emoji import OK, WARN
from app.keyboards import GREEN, main_menu, reply_btn, subscribe_kb
from app.sharing import accept_gift, gift_token, ref_id, reward_referrer
from app.states import Registration
from app.subscription import check_subscription
from app.utils import HELP_TEXT, esc

router = Router(name="start")
router.message.filter(F.chat.type == "private")

VERIFY_TEXT = "Akkauntingizni tasdiqlang \U0001F447"

WELCOME = (
    "\U0001F44B Salom, <b>{name}</b>!\n\n"
    "Men <b>Eslatma bot</b>man. Biror narsani unutmasligingiz kerak bo'lsa, "
    "menga yozing. Vaqti kelganda o'zim eslataman \u23f0\n\n"
    "<b>Qanday ishlatiladi?</b>\n"
    "1\ufe0f\u20e3 Shunchaki yozing, masalan:\n"
    "<code>ertaga 9:00 dori ichish</code>\n"
    "<code>30 daqiqadan keyin choy</code>\n\n"
    "2\ufe0f\u20e3 Yoki pastdagi \u00ab\u2795 Eslatma yaratish\u00bb tugmasini bosing, "
    "men o'zim so'rab boraman.\n\n"
    "3\ufe0f\u20e3 Vaqti kelganda sizga xabar yuboraman. Xabar tagida "
    "\u00ab5 min\u00bb, \u00ab10 min\u00bb tugmalari bo'ladi. Hozir vaqtingiz yo'q bo'lsa, "
    "bosing, men yana eslataman.\n\n"
    "<b>Yana nimalar bor?</b>\n"
    "\U0001F501 Takroriy eslatma: har kuni yoki hafta kunlari\n"
    "\U0001F465 Do'stga eslatma: do'stingiz uchun eslatma yozasiz, u bossa "
    "eslatma uning telefoniga o'rnatiladi\n"
    "\U0001F381 Do'st taklif qilish: do'stingiz qo'shilsa, eslatma limitingiz oshadi\n\n"
    "Savol bo'lsa: /help"
)


def phone_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [reply_btn("\U0001F4F1 Telefon raqamni ulashish", GREEN, request_contact=True)]
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
    ref = ref_id(command.args)
    user = await db.get_user(message.from_user.id)
    if is_registered(user):
        if user.get("is_blocked"):
            await message.answer(
                "Sizning botdan foydalanishingiz cheklangan. "
                "Savol bo'lsa administratorga murojaat qiling."
            )
            return
        name = esc(message.from_user.first_name or "do'st")
        await message.answer(WELCOME.format(name=name), reply_markup=main_menu())
        if token:
            await accept_gift(message, bot, db, settings, token)
        return

    # Yangi foydalanuvchi: telefon orqali tasdiqlash
    await state.update_data(gift=token, ref=ref)
    await state.set_state(Registration.phone)
    text = VERIFY_TEXT
    if token:
        share = await db.get_share(token)
        if share and not share.get("claimed_by"):
            sender = esc(share.get("from_name") or "Do'stingiz")
            text = (
                f"\U0001F381 <b>{sender}</b> sizga eslatma yubordi.\n"
                f"Qabul qilish uchun {VERIFY_TEXT[0].lower()}{VERIFY_TEXT[1:]}"
            )
    await message.answer(text, reply_markup=phone_kb())


@router.message(Registration.phone, F.contact)
async def got_phone(
    message: Message, state: FSMContext, bot: Bot, db: Database, settings: Settings
):
    contact = message.contact
    if contact.user_id != message.from_user.id:
        await message.answer(
            "Faqat o'zingizning raqamingizni yuboring.", reply_markup=phone_kb()
        )
        return
    uid = message.from_user.id
    existing = await db.get_user(uid)
    data = await state.get_data()
    token = data.get("gift")
    ref = data.get("ref")

    # Taklif qilgan odam: o'zi emas, ro'yxatdan o'tgan va bu odam avval taklif qilinmagan
    referred_by = None
    if ref and ref != uid and not (existing and existing.get("referred_by")):
        if is_registered(await db.get_user(ref)):
            referred_by = ref

    await db.register_user(
        uid,
        message.from_user.full_name,
        message.from_user.username,
        contact.phone_number,
        referred_by,
    )
    await state.clear()
    name = esc(message.from_user.first_name or "do'st")
    await message.answer(
        f"{OK} Akkaunt tasdiqlandi.\n\n" + WELCOME.format(name=name),
        reply_markup=main_menu(),
    )
    if token:
        await accept_gift(message, bot, db, settings, token)
    if referred_by:
        await reward_referrer(bot, db, settings, referred_by, message.from_user)


@router.message(Registration.phone)
async def phone_required(message: Message):
    await message.answer(VERIFY_TEXT, reply_markup=phone_kb())


@router.callback_query(F.data == "sub:check")
async def cb_sub_check(call: CallbackQuery, bot: Bot, db: Database) -> None:
    """"Obuna bo'ldim" tugmasi: kanallarni qayta tekshiradi."""
    missing, _ = await check_subscription(bot, db, call.from_user.id, force=True)
    if missing:
        await call.answer(f"{WARN} Hali obuna bo'lmagansiz", show_alert=True)
        try:
            await call.message.edit_reply_markup(reply_markup=subscribe_kb(missing))
        except Exception:
            pass
        return
    await call.answer("Rahmat!")
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(
        f"{OK} Rahmat! Endi botdan foydalanishingiz mumkin.", reply_markup=main_menu()
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
    await message.answer(f"{OK} Bekor qilindi", reply_markup=main_menu())
