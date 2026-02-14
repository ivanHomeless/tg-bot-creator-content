import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message

logger = logging.getLogger(__name__)

MEDIA_GROUP_DELAY = 3.0  # seconds of silence before finalizing album


class MediaGroupMiddleware(BaseMiddleware):
    """Collect messages belonging to the same media_group_id.

    The first message in a media group passes through to the handler
    **immediately** (no waiting).  A background task collects the
    remaining messages and resolves an ``asyncio.Future`` accessible
    via ``data["album_future"]``.

    The handler should run its heavy work (AI pipeline, etc.) first,
    then ``await data["album_future"]`` to get the complete album.
    By that time the album is guaranteed to be ready.

    Single messages (no ``media_group_id``) pass through immediately
    with ``data["album_future"]`` set to ``None``.
    """

    def __init__(self) -> None:
        super().__init__()
        self._albums: Dict[str, list[Message]] = {}
        self._events: Dict[str, asyncio.Event] = {}
        self._futures: Dict[str, asyncio.Future[list[Message]]] = {}

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        media_group_id = event.media_group_id

        if media_group_id is None:
            data["album_future"] = None
            return await handler(event, data)

        is_first = media_group_id not in self._albums

        if is_first:
            self._albums[media_group_id] = []
            self._events[media_group_id] = asyncio.Event()
            self._futures[media_group_id] = asyncio.get_running_loop().create_future()
            asyncio.create_task(self._collect(media_group_id))

        self._albums[media_group_id].append(event)

        if not is_first:
            # Signal the collector that a new message arrived
            self._events[media_group_id].set()
            return None

        # First message passes through immediately
        data["album_future"] = self._futures[media_group_id]
        return await handler(event, data)

    async def _collect(self, media_group_id: str) -> None:
        """Wait until no new messages arrive for MEDIA_GROUP_DELAY seconds."""
        ev = self._events[media_group_id]
        while True:
            ev.clear()
            try:
                await asyncio.wait_for(ev.wait(), timeout=MEDIA_GROUP_DELAY)
                # New message arrived — reset the wait
            except asyncio.TimeoutError:
                # Silence for DELAY seconds — album is complete
                break

        album = self._albums.pop(media_group_id, [])
        self._events.pop(media_group_id, None)
        future = self._futures.pop(media_group_id, None)

        logger.info(
            "Media group %s collected %d message(s)", media_group_id, len(album),
        )

        if future and not future.done():
            future.set_result(album)
