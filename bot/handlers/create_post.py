import asyncio
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.keyboards.inline import post_actions_keyboard
from bot.keyboards.reply import BTN_CREATE_POST
from bot.states.fsm import CreatePost
from db.repo import Repository
from services.ai.graph import build_graph
from services.ai.prompts import DEFAULT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

router = Router()


def _extract_media_ids(messages: list[Message]) -> list[str]:
    """Extract media file_ids from a list of messages."""
    media_ids: list[str] = []
    for msg in messages:
        if msg.photo:
            media_ids.append(f"photo:{msg.photo[-1].file_id}")
        elif msg.video:
            media_ids.append(f"video:{msg.video.file_id}")
        elif msg.document:
            media_ids.append(f"document:{msg.document.file_id}")
    return media_ids


async def _generate_post(
    message: Message,
    repo: Repository,
    tavily_api_key: str,
    llm_router: object,
    album_future: asyncio.Future | None = None,
) -> None:
    """Shared logic: search + generate + save + send preview.

    If ``album_future`` is provided (media group), the AI pipeline runs
    first, then the future is awaited to get the collected album.
    This way media collection happens in parallel with generation.
    """
    product_query = message.text or message.caption or ""
    if not product_query.strip():
        await message.answer("Пожалуйста, укажите название товара текстом.")
        return

    # Status message
    status_msg = await message.answer("⏳ Собираю данные и генерирую пост...")

    # Load system prompt from DB (or use default)
    saved_prompt = await repo.get_setting("system_prompt")
    system_prompt = saved_prompt or DEFAULT_SYSTEM_PROMPT

    # Run AI pipeline (media collects in background during this)
    graph = build_graph(tavily_api_key, llm_router)
    result = await graph.ainvoke(
        {
            "product_query": product_query,
            "system_prompt": system_prompt,
        }
    )

    generated_text = result.get("generated_text", "")

    # Now get media — album is guaranteed to be ready by now
    if album_future is not None:
        album = await album_future
        media_ids = _extract_media_ids(album)
    else:
        media_ids = _extract_media_ids([message])

    logger.info("Post media_ids (%d): %s", len(media_ids), media_ids)

    # Save post to DB
    post = await repo.create_post(
        original_text=product_query,
        generated_text=generated_text,
        media_ids=media_ids or None,
    )

    # Delete status message
    try:
        await status_msg.delete()
    except Exception:
        pass

    # Send preview with inline buttons
    try:
        await message.answer(
            generated_text,
            reply_markup=post_actions_keyboard(post.id),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        await message.answer(
            generated_text,
            reply_markup=post_actions_keyboard(post.id),
        )


# ---- Private chat: button → FSM → generate ----

@router.message(F.text == BTN_CREATE_POST)
async def start_create_post(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(CreatePost.waiting_for_input)
    await message.answer(
        "Отправьте название товара.\n"
        "Можно также приложить фото или видео (альбом)."
    )


@router.message(CreatePost.waiting_for_input)
async def process_create_post(
    message: Message,
    state: FSMContext,
    repo: Repository,
    tavily_api_key: str,
    llm_router: object,
    album_future: asyncio.Future | None = None,
) -> None:
    await state.clear()
    await _generate_post(message, repo, tavily_api_key, llm_router, album_future)


# ---- Group: any message with text or media+caption → generate immediately ----

def _is_group_content(message: Message) -> bool:
    """Match group messages that have text (not a command) or media with caption."""
    if message.chat.type not in ("group", "supergroup"):
        return False
    if message.text:
        return not message.text.startswith("/")
    # Photo/video/document with caption
    if message.caption and (message.photo or message.video or message.document):
        return True
    return False


@router.message(StateFilter(None), _is_group_content)
async def group_create_post(
    message: Message,
    repo: Repository,
    tavily_api_key: str,
    llm_router: object,
    album_future: asyncio.Future | None = None,
) -> None:
    await _generate_post(message, repo, tavily_api_key, llm_router, album_future)
