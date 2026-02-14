import json
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
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
    album: list[Message] | None = None,
) -> None:
    # Extract product query text
    product_query = message.text or message.caption or ""
    if not product_query.strip():
        await message.answer("Пожалуйста, укажите название товара текстом.")
        return

    # Extract media file_ids from album
    media_ids: list[str] = []
    messages_to_scan = album if album else [message]
    for msg in messages_to_scan:
        if msg.photo:
            media_ids.append(f"photo:{msg.photo[-1].file_id}")
        elif msg.video:
            media_ids.append(f"video:{msg.video.file_id}")
        elif msg.document:
            media_ids.append(f"document:{msg.document.file_id}")

    # Status message
    status_msg = await message.answer("⏳ Собираю данные и генерирую пост...")

    # Load system prompt from DB (or use default)
    saved_prompt = await repo.get_setting("system_prompt")
    system_prompt = saved_prompt or DEFAULT_SYSTEM_PROMPT

    # Run AI pipeline
    graph = build_graph(tavily_api_key, llm_router)
    result = await graph.ainvoke(
        {
            "product_query": product_query,
            "system_prompt": system_prompt,
        }
    )

    generated_text = result.get("generated_text", "")

    # Save post to DB
    post = await repo.create_post(
        original_text=product_query,
        generated_text=generated_text,
        media_ids=media_ids or None,
    )

    await state.clear()

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
