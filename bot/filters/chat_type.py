from aiogram.filters import Filter
from aiogram.types import Message


class IsPrivateChat(Filter):
    async def __call__(self, message: Message) -> bool:
        return message.chat.type == "private"
