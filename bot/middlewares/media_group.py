import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message

logger = logging.getLogger(__name__)

MEDIA_GROUP_DELAY = 2.0  # seconds to wait for more messages in a media group


class MediaGroupMiddleware(BaseMiddleware):
    """Collect messages belonging to the same media_group_id.

    Buffers incoming messages for ``MEDIA_GROUP_DELAY`` seconds, then
    passes the full album (list of Messages) to the handler via
    ``data["album"]``.  Only the first message in a group triggers the
    handler; subsequent messages are silently collected.

    Single messages (no ``media_group_id``) pass through immediately
    with ``data["album"]`` set to ``None``.
    """

    def __init__(self) -> None:
        super().__init__()
        self._albums: Dict[str, list[Message]] = {}
        self._timers: Dict[str, asyncio.TimerHandle] = {}
        self._futures: Dict[str, asyncio.Future[list[Message]]] = {}

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        media_group_id = event.media_group_id

        if media_group_id is None:
            data["album"] = None
            return await handler(event, data)

        is_first = media_group_id not in self._albums

        # Accumulate message
        if is_first:
            self._albums[media_group_id] = []
        self._albums[media_group_id].append(event)

        # Reset timer on every new message (extend the window)
        if media_group_id in self._timers:
            self._timers[media_group_id].cancel()

        if is_first:
            loop = asyncio.get_running_loop()
            self._futures[media_group_id] = loop.create_future()

        # Schedule finalization
        loop = asyncio.get_running_loop()
        self._timers[media_group_id] = loop.call_later(
            MEDIA_GROUP_DELAY,
            self._finalize,
            media_group_id,
        )

        if not is_first:
            # Not the first message — just collected, don't call handler
            return None

        # First message waits for the album to be finalized
        album = await self._futures[media_group_id]
        data["album"] = album
        return await handler(event, data)

    def _finalize(self, media_group_id: str) -> None:
        """Called by the timer when no more messages arrive."""
        album = self._albums.pop(media_group_id, [])
        self._timers.pop(media_group_id, None)
        future = self._futures.pop(media_group_id, None)

        if future and not future.done():
            future.set_result(album)
        else:
            logger.warning(
                "Media group %s: future already done or missing", media_group_id
            )
