import math

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.keyboards.inline import post_actions_keyboard, queue_keyboard
from bot.keyboards.reply import BTN_QUEUE
from db.repo import Repository

router = Router()

POSTS_PER_PAGE = 5


def _truncate(text: str, length: int = 40) -> str:
    if len(text) <= length:
        return text
    return text[:length - 1] + "…"


async def _show_queue_page(
    target, repo: Repository, page: int, edit: bool = False
) -> None:
    """Render a queue page. ``target`` is Message or CallbackQuery.message."""
    total = await repo.count_approved_posts()
    total_pages = max(1, math.ceil(total / POSTS_PER_PAGE))
    page = max(1, min(page, total_pages))

    if total == 0:
        text = "Очередь пуста."
        if edit:
            await target.edit_text(text, reply_markup=None)
        else:
            await target.answer(text)
        return

    posts = await repo.get_approved_posts(page=page, per_page=POSTS_PER_PAGE)
    items = [(p.id, _truncate(p.generated_text or p.original_text)) for p in posts]
    keyboard = queue_keyboard(items, page, total_pages)

    text = f"📋 <b>Очередь постов</b> ({total} шт.)"
    if edit:
        await target.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await target.answer(text, reply_markup=keyboard, parse_mode="HTML")


# ---- entry: reply button ----

@router.message(F.text == BTN_QUEUE)
async def cmd_queue(message: Message, repo: Repository) -> None:
    await _show_queue_page(message, repo, page=1)


# ---- pagination callback ----

@router.callback_query(F.data.startswith("queue:page:"))
async def on_queue_page(callback: CallbackQuery, repo: Repository) -> None:
    page = int(callback.data.split(":")[2])
    await _show_queue_page(callback.message, repo, page, edit=True)
    await callback.answer()


# ---- post detail callback ----

@router.callback_query(F.data.startswith("queue:post:"))
async def on_queue_post_detail(
    callback: CallbackQuery, repo: Repository
) -> None:
    post_id = int(callback.data.split(":")[2])
    post = await repo.get_post(post_id)

    if post is None:
        await callback.answer("Пост не найден")
        return

    text = post.generated_text or post.original_text or "(пусто)"
    keyboard = post_actions_keyboard(post_id)

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()
