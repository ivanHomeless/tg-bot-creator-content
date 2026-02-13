from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.keyboards.reply import main_menu_keyboard

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if message.chat.type == "private":
        await message.answer(
            "Привет! Я бот для создания постов в канал.\n"
            "Выберите действие из меню ниже.",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await message.answer(
            "Привет! Отправьте мне /start в личных сообщениях "
            "для полного доступа к функциям."
        )
