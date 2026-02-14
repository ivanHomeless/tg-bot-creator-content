import logging
from typing import Any, Callable, Coroutine

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.inline import post_actions_keyboard
from bot.states.fsm import EditPost, RewritePost
from db.models import PostStatus
from db.repo import Repository

logger = logging.getLogger(__name__)

router = Router()


# ---- helpers ----

def _parse_post_callback(data: str) -> tuple[int, str] | None:
    """Parse 'post:{id}:{action}' → (post_id, action) or None."""
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "post":
        return None
    try:
        return int(parts[1]), parts[2]
    except ValueError:
        return None


# ---- main callback dispatcher ----

@router.callback_query(F.data.startswith("post:"))
async def on_post_action(
    callback: CallbackQuery,
    state: FSMContext,
    repo: Repository,
    publish_post: Callable[..., Coroutine] | None = None,
    llm_router: object | None = None,
) -> None:
    parsed = _parse_post_callback(callback.data)
    if not parsed:
        await callback.answer("Неизвестная команда")
        return

    post_id, action = parsed
    post = await repo.get_post(post_id)

    if post is None:
        await callback.answer("Пост не найден")
        return

    # Block actions on a post that is currently being edited
    if post.status == PostStatus.editing.value and action not in ("delete",):
        await callback.answer("Пост сейчас редактируется, подождите.")
        return

    if action == "publish":
        await _handle_publish(callback, repo, post_id, publish_post)
    elif action == "approve":
        await _handle_approve(callback, repo, post_id)
    elif action == "edit":
        await _handle_edit(callback, state, repo, post_id)
    elif action == "rewrite":
        await _handle_rewrite(callback, state, repo, post_id)
    elif action == "delete":
        await _handle_delete(callback, repo, post_id)
    else:
        await callback.answer("Неизвестное действие")


# ---- action implementations ----

async def _handle_publish(
    callback: CallbackQuery,
    repo: Repository,
    post_id: int,
    publish_post: Callable[..., Coroutine] | None,
) -> None:
    post = await repo.get_post(post_id)
    if publish_post and post:
        await publish_post(post)
    await repo.update_post_status(post_id, PostStatus.published)
    await callback.message.edit_text(
        f"{callback.message.text}\n\n✅ Опубликовано!",
        reply_markup=None,
    )
    await callback.answer("Опубликовано")


async def _handle_approve(
    callback: CallbackQuery,
    repo: Repository,
    post_id: int,
) -> None:
    await repo.update_post_status(post_id, PostStatus.approved)
    await callback.message.edit_text(
        f"{callback.message.text}\n\n✅ Добавлено в очередь!",
        reply_markup=None,
    )
    await callback.answer("Добавлено в очередь")


async def _handle_edit(
    callback: CallbackQuery,
    state: FSMContext,
    repo: Repository,
    post_id: int,
) -> None:
    await repo.update_post_status(post_id, PostStatus.editing)
    await state.set_state(EditPost.waiting_for_text)
    await state.update_data(edit_post_id=post_id)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "Отправьте новый текст поста."
    )
    await callback.answer()


async def _handle_rewrite(
    callback: CallbackQuery,
    state: FSMContext,
    repo: Repository,
    post_id: int,
) -> None:
    await repo.update_post_status(post_id, PostStatus.editing)
    await state.set_state(RewritePost.waiting_for_prompt)
    await state.update_data(rewrite_post_id=post_id)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "Отправьте дополнительные инструкции для переписывания поста."
    )
    await callback.answer()


async def _handle_delete(
    callback: CallbackQuery,
    repo: Repository,
    post_id: int,
) -> None:
    await repo.delete_post(post_id)
    await callback.message.edit_text("🗑 Пост удалён.", reply_markup=None)
    await callback.answer("Удалено")


# ---- FSM handlers for edit / rewrite ----

@router.message(EditPost.waiting_for_text)
async def on_edit_text(
    message: Message,
    state: FSMContext,
    repo: Repository,
) -> None:
    data = await state.get_data()
    post_id = data.get("edit_post_id")
    if not post_id:
        await state.clear()
        return

    new_text = message.text or ""
    if not new_text.strip():
        await message.answer("Отправьте текст.")
        return

    await repo.update_post_text(post_id, new_text)
    await repo.update_post_status(post_id, PostStatus.pending)
    await state.clear()

    await message.answer(
        new_text,
        reply_markup=post_actions_keyboard(post_id),
        parse_mode="HTML",
    )


@router.message(RewritePost.waiting_for_prompt)
async def on_rewrite_prompt(
    message: Message,
    state: FSMContext,
    repo: Repository,
    llm_router: object | None = None,
) -> None:
    data = await state.get_data()
    post_id = data.get("rewrite_post_id")
    if not post_id:
        await state.clear()
        return

    prompt = message.text or ""
    if not prompt.strip():
        await message.answer("Отправьте инструкции для переписывания.")
        return

    post = await repo.get_post(post_id)
    if not post or not llm_router:
        await state.clear()
        await message.answer("Ошибка: пост не найден или LLM недоступен.")
        return

    status_msg = await message.answer("⏳ Переписываю пост...")

    messages = [
        {"role": "system", "content": "Перепиши пост по инструкции пользователя."},
        {
            "role": "user",
            "content": (
                f"Текущий текст поста:\n{post.generated_text}\n\n"
                f"Инструкция: {prompt}"
            ),
        },
    ]

    try:
        response = await llm_router.generate(messages)
        new_text = response.text
    except Exception as e:
        logger.error("Rewrite failed: %s", e)
        new_text = post.generated_text  # keep original on failure

    await repo.update_post_text(post_id, new_text)
    await repo.update_post_status(post_id, PostStatus.pending)
    await state.clear()

    try:
        await status_msg.delete()
    except Exception:
        pass

    await message.answer(
        new_text,
        reply_markup=post_actions_keyboard(post_id),
        parse_mode="HTML",
    )
