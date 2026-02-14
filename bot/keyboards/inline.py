from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def post_actions_keyboard(post_id: int) -> InlineKeyboardMarkup:
    """5-button panel for a single post preview."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Опубликовать",
                    callback_data=f"post:{post_id}:publish",
                ),
                InlineKeyboardButton(
                    text="✅ В очередь",
                    callback_data=f"post:{post_id}:approve",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Редактировать",
                    callback_data=f"post:{post_id}:edit",
                ),
                InlineKeyboardButton(
                    text="🔄 Переписать",
                    callback_data=f"post:{post_id}:rewrite",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Удалить",
                    callback_data=f"post:{post_id}:delete",
                ),
            ],
        ]
    )


def queue_keyboard(
    posts: list[tuple[int, str]], page: int, total_pages: int
) -> InlineKeyboardMarkup:
    """Queue navigation: numbered posts + prev/next buttons.

    ``posts`` is a list of ``(post_id, short_label)`` tuples for the
    current page.
    """
    rows: list[list[InlineKeyboardButton]] = []

    for idx, (post_id, label) in enumerate(posts, start=1):
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{idx}. {label}",
                    callback_data=f"queue:post:{post_id}",
                )
            ]
        )

    nav_row: list[InlineKeyboardButton] = []
    if page > 1:
        nav_row.append(
            InlineKeyboardButton(text="⬅️", callback_data=f"queue:page:{page - 1}")
        )
    nav_row.append(
        InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop")
    )
    if page < total_pages:
        nav_row.append(
            InlineKeyboardButton(text="➡️", callback_data=f"queue:page:{page + 1}")
        )
    rows.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📝 Промпт", callback_data="settings:prompt"
                ),
                InlineKeyboardButton(
                    text="⏰ Расписание", callback_data="settings:schedule"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🤖 Провайдеры", callback_data="settings:providers"
                ),
                InlineKeyboardButton(
                    text="💬 Чаты", callback_data="settings:chats"
                ),
            ],
        ]
    )


def chats_keyboard(chats: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    """Keyboard for managing allowed chats.

    ``chats`` is a list of ``(db_id, display_label)`` tuples.
    """
    rows: list[list[InlineKeyboardButton]] = []

    for db_id, label in chats:
        rows.append([
            InlineKeyboardButton(text=label, callback_data="noop"),
            InlineKeyboardButton(
                text="❌", callback_data=f"chats:remove:{db_id}",
            ),
        ])

    rows.append([
        InlineKeyboardButton(text="➕ Добавить чат", callback_data="chats:add"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)
