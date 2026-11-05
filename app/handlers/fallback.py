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
        await message.answer(
            "Iltimos, so'ralgan ma'lumotni matn ko'rinishida yuboring "
            "yoki /cancel bosing."
        )
        return
    await message.answer(
        "Quyidagi tugmalardan foydalaning:", reply_markup=main_menu()
    )
