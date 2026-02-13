import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message

logger = logging.getLogger(__name__)

MEDIA_GROUP_DELAY = 1.5  # seconds to wait for more messages in a media group


class MediaGroupMiddleware(BaseMiddleware):
    """Collect messages belonging to the same media_group_id.

    Buffers incoming messages for ``MEDIA_GROUP_DELAY`` seconds, then
    passes the full album (list of Messages) to the handler via
    ``data["album"]``.  Single messages (no ``media_group_id``) pass
    through immediately with ``data["album"]`` containing just that one
    message.
    """

    def __init__(self) -> None:
        super().__init__()
        self._albums: Dict[str, list[Message]] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        media_group_id = event.media_group_id

        if media_group_id is None:
            data["album"] = [event]
            return await handler(event, data)

        # First message in this group creates the lock
        if media_group_id not in self._locks:
            self._locks[media_group_id] = asyncio.Lock()

        if media_group_id not in self._albums:
            self._albums[media_group_id] = []

        self._albums[media_group_id].append(event)

        # Only the first message triggers the delayed handler call
        if len(self._albums[media_group_id]) > 1:
            return None

        await asyncio.sleep(MEDIA_GROUP_DELAY)

        album = self._albums.pop(media_group_id, [])
        self._locks.pop(media_group_id, None)

        data["album"] = album
        return await handler(event, data)
