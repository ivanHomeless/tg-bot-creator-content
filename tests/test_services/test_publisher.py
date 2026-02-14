import pytest
from unittest.mock import AsyncMock, MagicMock

from aiogram.exceptions import TelegramRetryAfter

from services.publisher import publish_post, MAX_CAPTION_LENGTH


def _make_post(text="Post text", media_ids=None):
    post = MagicMock()
    post.generated_text = text
    post.media_ids = media_ids
    return post


def _make_bot():
    bot = AsyncMock()
    sent_msg = MagicMock()
    sent_msg.message_id = 100
    bot.send_message.return_value = sent_msg
    bot.send_photo.return_value = sent_msg
    bot.send_video.return_value = sent_msg
    bot.send_document.return_value = sent_msg
    bot.send_media_group.return_value = [sent_msg]
    return bot


CHANNEL_ID = -1001234567890


class TestPublisher:
    async def test_publish_text_only(self):
        """No media → send_message."""
        bot = _make_bot()
        post = _make_post("Hello world")

        await publish_post(bot, post, CHANNEL_ID)

        bot.send_message.assert_called_once_with(
            CHANNEL_ID, "Hello world", parse_mode="HTML"
        )

    async def test_publish_short_text_with_media(self):
        """Single photo + short text → send_photo with caption."""
        bot = _make_bot()
        post = _make_post("Short caption", media_ids=["photo:abc123"])

        await publish_post(bot, post, CHANNEL_ID)

        bot.send_photo.assert_called_once_with(
            CHANNEL_ID, "abc123", caption="Short caption", parse_mode="HTML"
        )

    async def test_publish_long_text_with_media(self):
        """Single photo + long text → photo without caption, then reply."""
        bot = _make_bot()
        long_text = "A" * (MAX_CAPTION_LENGTH + 1)
        post = _make_post(long_text, media_ids=["photo:abc123"])

        await publish_post(bot, post, CHANNEL_ID)

        # Photo sent without caption
        bot.send_photo.assert_called_once_with(CHANNEL_ID, "abc123")
        # Then reply with text
        bot.send_message.assert_called_once_with(
            CHANNEL_ID, long_text,
            parse_mode="HTML", reply_to_message_id=100,
        )

    async def test_publish_media_group(self):
        """Multiple media → send_media_group with caption on first item."""
        bot = _make_bot()
        post = _make_post(
            "Group caption",
            media_ids=["photo:id1", "video:id2", "photo:id3"],
        )

        await publish_post(bot, post, CHANNEL_ID)

        bot.send_media_group.assert_called_once()
        call_args = bot.send_media_group.call_args
        items = call_args[0][1]
        assert len(items) == 3
        # First item has caption
        assert items[0].caption == "Group caption"
        # Others don't
        assert items[1].caption is None
        assert items[2].caption is None

    async def test_flood_wait_retry(self):
        """First call raises TelegramRetryAfter, second succeeds."""
        bot = _make_bot()
        error = TelegramRetryAfter(retry_after=0.01, method=MagicMock(), message="flood")
        sent_msg = MagicMock()
        sent_msg.message_id = 100
        bot.send_message.side_effect = [error, sent_msg]

        post = _make_post("Retry test")

        await publish_post(bot, post, CHANNEL_ID)

        assert bot.send_message.call_count == 2

    async def test_flood_wait_max_retries_exceeded(self):
        """All retries raise TelegramRetryAfter → exception propagated."""
        bot = _make_bot()
        error = TelegramRetryAfter(retry_after=0.01, method=MagicMock(), message="flood")
        bot.send_message.side_effect = [error, error, error]

        post = _make_post("Fail test")

        with pytest.raises(TelegramRetryAfter):
            await publish_post(bot, post, CHANNEL_ID)

        assert bot.send_message.call_count == 3
