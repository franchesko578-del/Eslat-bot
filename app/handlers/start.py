"""/start, /help, /cancel va bekor qilish tugmasi."""
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.emoji import OK, WAVE
from app.keyboards import main_menu
from app.utils import HELP_TEXT, esc

router = Router(name="start")
router.message.filter(F.chat.type == "private")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    name = esc(message.from_user.first_name or "do'st")
    await message.answer(
        f"{WAVE} Salom, <b>{name}</b>!\n\n"
        "Men <b>ESLATMA BOT</b>man. Kerakli vaqtda sizga eslatma "
        "yuboraman.\n\nQuyidagi tugmalardan birini tanlang:",
        reply_markup=main_menu(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=main_menu())


@router.message(Command("cancel"))
@router.message(F.text.endswith("Bekor qilish"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(f"{OK} Bekor qilindi.", reply_markup=main_menu())
