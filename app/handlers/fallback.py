"""Boshqa hech narsaga mos kelmagan xabarlar."""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.keyboards import main_menu

router = Router(name="fallback")
router.message.filter(F.chat.type == "private")


@router.message()
async def unknown_message(message: Message, state: FSMContext) -> None:
    if await state.get_state() is not None:
        await message.answer("✍️ Matn yuboring yoki /cancel bosing.")
        return
    await message.answer("👇 Menyudan tanlang", reply_markup=main_menu())
