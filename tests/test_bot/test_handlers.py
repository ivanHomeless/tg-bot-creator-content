import pytest
from unittest.mock import AsyncMock, MagicMock

from aiogram.types import ReplyKeyboardMarkup

from bot.handlers.start import cmd_start


def _make_message(chat_type: str = "private") -> MagicMock:
    """Create a mock Message with the given chat type."""
    msg = AsyncMock()
    msg.chat = MagicMock()
    msg.chat.type = chat_type
    msg.answer = AsyncMock()
    return msg


class TestStartHandler:
    async def test_start_private_sends_menu(self):
        """/start in private chat → answer with ReplyKeyboardMarkup."""
        msg = _make_message("private")

        await cmd_start(msg)

        msg.answer.assert_called_once()
        kwargs = msg.answer.call_args
        reply_markup = kwargs.kwargs.get("reply_markup") or kwargs[1].get("reply_markup")
        assert isinstance(reply_markup, ReplyKeyboardMarkup)

    async def test_start_group_no_reply_keyboard(self):
        """/start in group → answer without ReplyKeyboardMarkup."""
        msg = _make_message("group")

        await cmd_start(msg)

        msg.answer.assert_called_once()
        kwargs = msg.answer.call_args
        # No reply_markup kwarg or it's not a ReplyKeyboardMarkup
        reply_markup = kwargs.kwargs.get("reply_markup") or kwargs[1].get("reply_markup") if kwargs[1] else None
        assert reply_markup is None or not isinstance(reply_markup, ReplyKeyboardMarkup)
