from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_CREATE_POST = "📝 Создать пост"
BTN_QUEUE = "🗂 Очередь постов"
BTN_SETTINGS = "⚙️ Настройки"


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CREATE_POST)],
            [KeyboardButton(text=BTN_QUEUE), KeyboardButton(text=BTN_SETTINGS)],
        ],
        resize_keyboard=True,
    )
