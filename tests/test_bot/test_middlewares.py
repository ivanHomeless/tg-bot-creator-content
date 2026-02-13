import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock

from bot.middlewares.access import AllowedChatsMiddleware
from bot.middlewares.media_group import MediaGroupMiddleware


# --------------- AllowedChatsMiddleware ---------------


class TestAllowedChatsMiddleware:
    async def test_allowed_chat_passes_through(self):
        """Handler IS called when chat is in allowed list."""
        middleware = AllowedChatsMiddleware()

        event = MagicMock()
        event.chat.id = 123

        repo = AsyncMock()
        repo.is_chat_allowed.return_value = True

        handler = AsyncMock(return_value="ok")
        data = {"repo": repo}

        result = await middleware(handler, event, data)

        handler.assert_called_once_with(event, data)
        assert result == "ok"

    async def test_disallowed_chat_blocked(self):
        """Handler is NOT called when chat is not in allowed list."""
        middleware = AllowedChatsMiddleware()

        event = MagicMock()
        event.chat.id = 456

        repo = AsyncMock()
        repo.is_chat_allowed.return_value = False

        handler = AsyncMock()
        data = {"repo": repo}

        result = await middleware(handler, event, data)

        handler.assert_not_called()
        assert result is None

    async def test_no_chat_attr_passes_through(self):
        """Events without .chat attribute pass through (e.g. inline queries)."""
        middleware = AllowedChatsMiddleware()

        event = MagicMock(spec=[])  # no attributes at all
        repo = AsyncMock()
        handler = AsyncMock(return_value="ok")
        data = {"repo": repo}

        result = await middleware(handler, event, data)

        handler.assert_called_once()
        assert result == "ok"


# --------------- MediaGroupMiddleware ---------------


class TestMediaGroupMiddleware:
    async def test_media_group_collects_album(self):
        """3 messages with same media_group_id → handler gets album of 3."""
        middleware = MediaGroupMiddleware()
        handler = AsyncMock()

        messages = []
        for i in range(3):
            msg = MagicMock()
            msg.media_group_id = "album_123"
            msg.message_id = i
            messages.append(msg)

        # Send all 3 messages concurrently (simulating rapid arrival)
        tasks = [
            asyncio.create_task(
                middleware(handler, msg, {"extra": "data"})
            )
            for msg in messages
        ]
        await asyncio.gather(*tasks)

        # Handler called only once with album of 3
        handler.assert_called_once()
        call_data = handler.call_args[1] if handler.call_args[1] else handler.call_args[0][1]
        assert len(call_data["album"]) == 3

    async def test_media_group_single_message(self):
        """Message without media_group_id passes through immediately."""
        middleware = MediaGroupMiddleware()
        handler = AsyncMock(return_value="ok")

        msg = MagicMock()
        msg.media_group_id = None

        result = await middleware(handler, msg, {})

        handler.assert_called_once()
        call_data = handler.call_args[0][1]
        assert call_data["album"] == [msg]
        assert result == "ok"
