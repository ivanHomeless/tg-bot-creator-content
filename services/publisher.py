import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import InputMediaDocument, InputMediaPhoto, InputMediaVideo

from db.models import Post

logger = logging.getLogger(__name__)

MAX_CAPTION_LENGTH = 1024
MAX_RETRIES = 3


def _parse_media_id(raw: str) -> tuple[str, str]:
    """Parse 'type:file_id' → (type, file_id)."""
    kind, _, file_id = raw.partition(":")
    return kind, file_id


def _build_input_media(kind: str, file_id: str, caption: str | None = None):
    """Build an aiogram InputMedia* object."""
    if kind == "photo":
        return InputMediaPhoto(media=file_id, caption=caption, parse_mode="HTML")
    elif kind == "video":
        return InputMediaVideo(media=file_id, caption=caption, parse_mode="HTML")
    elif kind == "document":
        return InputMediaDocument(media=file_id, caption=caption, parse_mode="HTML")
    else:
        return InputMediaDocument(media=file_id, caption=caption, parse_mode="HTML")


async def _send_with_retry(coro_fn, *args, **kwargs):
    """Call an async function with FloodWait retry (max MAX_RETRIES)."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await coro_fn(*args, **kwargs)
        except TelegramRetryAfter as e:
            if attempt >= MAX_RETRIES:
                raise
            logger.warning(
                "FloodWait: retry after %s seconds (attempt %d/%d)",
                e.retry_after, attempt, MAX_RETRIES,
            )
            await asyncio.sleep(e.retry_after)


async def publish_post(bot: Bot, post: Post, channel_id: int) -> None:
    """Publish a post to the Telegram channel.

    Logic:
    - No media → send_message(text)
    - Single media + text ≤ 1024 → single media with caption
    - Multiple media + text ≤ 1024 → media_group, first item has caption
    - Media + text > 1024 → media (no caption), then reply with text
    """
    text = post.generated_text or ""
    media_ids: list[str] = post.media_ids or []

    if not media_ids:
        # Text only
        try:
            await _send_with_retry(
                bot.send_message, channel_id, text, parse_mode="HTML"
            )
        except TelegramBadRequest:
            logger.warning("HTML parse failed, sending as plain text")
            await _send_with_retry(
                bot.send_message, channel_id, text
            )
        return

    if len(media_ids) == 1:
        kind, file_id = _parse_media_id(media_ids[0])
        if len(text) <= MAX_CAPTION_LENGTH:
            if kind == "photo":
                await _send_with_retry(
                    bot.send_photo, channel_id, file_id,
                    caption=text, parse_mode="HTML",
                )
            elif kind == "video":
                await _send_with_retry(
                    bot.send_video, channel_id, file_id,
                    caption=text, parse_mode="HTML",
                )
            else:
                await _send_with_retry(
                    bot.send_document, channel_id, file_id,
                    caption=text, parse_mode="HTML",
                )
        else:
            # Single media without caption, then reply
            if kind == "photo":
                sent = await _send_with_retry(bot.send_photo, channel_id, file_id)
            elif kind == "video":
                sent = await _send_with_retry(bot.send_video, channel_id, file_id)
            else:
                sent = await _send_with_retry(bot.send_document, channel_id, file_id)
            await _send_with_retry(
                bot.send_message, channel_id, text,
                parse_mode="HTML", reply_to_message_id=sent.message_id,
            )
        return

    # Multiple media → media group
    items = []
    for i, raw in enumerate(media_ids):
        kind, file_id = _parse_media_id(raw)
        caption = text if i == 0 and len(text) <= MAX_CAPTION_LENGTH else None
        items.append(_build_input_media(kind, file_id, caption=caption))

    sent_messages = await _send_with_retry(
        bot.send_media_group, channel_id, items
    )

    if len(text) > MAX_CAPTION_LENGTH:
        first_msg = sent_messages[0]
        await _send_with_retry(
            bot.send_message, channel_id, text,
            parse_mode="HTML", reply_to_message_id=first_msg.message_id,
        )
