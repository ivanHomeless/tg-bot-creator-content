import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from db.repo import Repository

logger = logging.getLogger(__name__)


class AllowedChatsMiddleware(BaseMiddleware):
    """Drop updates from chats not in the allowed_chats table."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        repo: Repository = data["repo"]
        chat = getattr(event, "chat", None)
        if chat is None:
            return await handler(event, data)

        if await repo.is_chat_allowed(chat.id):
            return await handler(event, data)

        logger.debug("Chat %s not in allowed list, dropping update", chat.id)
        return None
