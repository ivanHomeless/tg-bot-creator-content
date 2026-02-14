import json
import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    Message,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bot.keyboards.inline import settings_keyboard, chats_keyboard
from bot.keyboards.reply import BTN_SETTINGS
from bot.states.fsm import EditPrompt, EditProviders, EditSchedule, AddChat
from db.repo import Repository
from services.scheduler import reschedule

logger = logging.getLogger(__name__)

router = Router()


# ---- entry ----

@router.message(F.text == BTN_SETTINGS)
async def cmd_settings(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("⚙️ Настройки", reply_markup=settings_keyboard())


# ========== PROMPT ==========

@router.callback_query(F.data == "settings:prompt")
async def on_edit_prompt_start(
    callback: CallbackQuery, state: FSMContext, repo: Repository
) -> None:
    current = await repo.get_setting("system_prompt")
    if current:
        file = BufferedInputFile(
            current.encode("utf-8"), filename="system_prompt.txt"
        )
        await callback.message.answer_document(file, caption="Текущий промпт")
    await state.set_state(EditPrompt.waiting_for_prompt)
    await callback.message.answer(
        "Отправьте новый промпт в виде .txt файла.",
    )
    await callback.answer()


@router.message(EditPrompt.waiting_for_prompt, F.document)
async def on_prompt_document(
    message: Message, state: FSMContext, repo: Repository, bot: Bot
) -> None:
    doc = message.document
    if not doc.file_name.endswith(".txt"):
        await message.answer("Поддерживаются только .txt файлы.")
        return

    file = await bot.download(doc)
    text = file.read().decode("utf-8", errors="replace")
    if not text.strip():
        await message.answer("Файл пустой. Отправьте файл с текстом.")
        return

    await repo.set_setting("system_prompt", text)
    await state.clear()
    await message.answer("✅ Промпт обновлён.")


@router.message(EditPrompt.waiting_for_prompt)
async def on_prompt_not_a_file(message: Message) -> None:
    await message.answer("Отправьте .txt файл с промптом.")


# ========== SCHEDULE ==========

@router.callback_query(F.data == "settings:schedule")
async def on_edit_schedule_start(
    callback: CallbackQuery, state: FSMContext, repo: Repository
) -> None:
    current = await repo.get_setting("cron_schedule")
    text = "Текущее расписание: "
    text += f"<code>{current}</code>" if current else "<i>не задано</i>"
    text += "\n\nОтправьте новое cron-выражение (например, <code>0 9 * * *</code>)."
    await callback.message.answer(text, parse_mode="HTML")
    await state.set_state(EditSchedule.waiting_for_cron)
    await callback.answer()


@router.message(EditSchedule.waiting_for_cron)
async def on_schedule_input(
    message: Message, state: FSMContext, repo: Repository,
    scheduler: AsyncIOScheduler,
) -> None:
    cron_expr = message.text.strip() if message.text else ""

    # Validate cron expression
    try:
        CronTrigger.from_crontab(cron_expr)
    except (ValueError, TypeError) as e:
        await message.answer(
            f"❌ Невалидное cron-выражение: <code>{cron_expr}</code>\n"
            f"Ошибка: {e}\n\nПопробуйте ещё раз.",
            parse_mode="HTML",
        )
        return

    await repo.set_setting("cron_schedule", cron_expr)
    reschedule(scheduler, cron_expr)
    await state.clear()
    await message.answer(f"✅ Расписание обновлено: <code>{cron_expr}</code>", parse_mode="HTML")


# ========== PROVIDERS ==========

@router.callback_query(F.data == "settings:providers")
async def on_edit_providers_start(
    callback: CallbackQuery, state: FSMContext, repo: Repository
) -> None:
    current = await repo.get_setting("llm_providers")
    if current and current != "[]":
        pretty = json.dumps(json.loads(current), indent=2, ensure_ascii=False)
        file = BufferedInputFile(
            pretty.encode("utf-8"), filename="llm_providers.json"
        )
        await callback.message.answer_document(file, caption="Текущий конфиг провайдеров")
    else:
        await callback.message.answer("Конфиг провайдеров пока не задан.")

    await callback.message.answer(
        "Отправьте .json файл с новым конфигом провайдеров."
    )
    await state.set_state(EditProviders.waiting_for_json)
    await callback.answer()


@router.message(EditProviders.waiting_for_json, F.document)
async def on_providers_json_file(
    message: Message, state: FSMContext, repo: Repository, bot: Bot,
) -> None:
    doc = message.document
    if not doc.file_name.endswith(".json"):
        await message.answer("Отправьте файл с расширением .json.")
        return

    file = await bot.download(doc)
    raw = file.read().decode("utf-8", errors="replace")

    # Validate JSON structure
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        await message.answer(
            f"❌ Невалидный JSON: {e}\nОтправьте исправленный файл."
        )
        return

    if not isinstance(data, list):
        await message.answer(
            "❌ JSON должен быть массивом провайдеров.\nОтправьте исправленный файл."
        )
        return

    # Basic structure validation
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            await message.answer(
                f"❌ Элемент #{i + 1} должен быть объектом.\nОтправьте исправленный файл."
            )
            return
        if "type" not in item or "api_keys" not in item:
            await message.answer(
                f"❌ Элемент #{i + 1}: обязательные поля 'type' и 'api_keys'.\n"
                "Отправьте исправленный файл."
            )
            return

    providers_str = json.dumps(data, ensure_ascii=False)
    await repo.set_setting("llm_providers", providers_str)

    # Hot-reload: rebuild llm_router in the Dispatcher
    from main import _build_llm_router
    dp = router.parent_router
    if dp is not None:
        while dp.parent_router is not None:
            dp = dp.parent_router
        dp["llm_router"] = _build_llm_router(providers_str)

    await state.clear()
    await message.answer(f"✅ Конфиг провайдеров обновлён ({len(data)} шт.).")


@router.message(EditProviders.waiting_for_json)
async def on_providers_not_a_file(message: Message) -> None:
    await message.answer("Отправьте .json файл с конфигом провайдеров.")


# ========== CHATS ==========

async def _show_chats_list(target_msg, repo: Repository) -> None:
    """Send the list of allowed chats with management keyboard."""
    chats = await repo.get_all_allowed_chats()
    items = []
    for c in chats:
        label = c.description or (f"@{c.username}" if c.username else str(c.telegram_id))
        items.append((c.id, label))

    await target_msg.answer(
        "💬 Разрешённые чаты:" if items else "Список чатов пуст.",
        reply_markup=chats_keyboard(items),
    )


@router.callback_query(F.data == "settings:chats")
async def on_chats_start(
    callback: CallbackQuery, state: FSMContext, repo: Repository
) -> None:
    await state.clear()
    await _show_chats_list(callback.message, repo)
    await callback.answer()


@router.callback_query(F.data == "chats:add")
async def on_chat_add_start(
    callback: CallbackQuery, state: FSMContext
) -> None:
    await state.set_state(AddChat.waiting_for_input)
    await callback.message.answer(
        "Отправьте @username группы или числовой chat_id.\n"
        "Например: <code>@mygroup</code> или <code>-1001234567890</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AddChat.waiting_for_input)
async def on_chat_add_input(
    message: Message, state: FSMContext, repo: Repository, bot: Bot
) -> None:
    raw = (message.text or "").strip()
    if not raw:
        await message.answer("Отправьте @username или chat_id.")
        return

    username: str | None = None
    telegram_id: int | None = None

    if raw.startswith("@"):
        try:
            chat_info = await bot.get_chat(raw)
            telegram_id = chat_info.id
            username = raw.lstrip("@")
        except Exception:
            await message.answer(
                f"❌ Не удалось найти чат {raw}.\n"
                "Убедитесь, что бот добавлен в эту группу и username указан верно."
            )
            return
    else:
        try:
            telegram_id = int(raw)
        except ValueError:
            await message.answer("❌ Некорректный формат. Отправьте @username или числовой chat_id.")
            return
        try:
            chat_info = await bot.get_chat(telegram_id)
            username = (chat_info.username or "").lstrip("@") or None
        except Exception:
            pass

    if await repo.is_chat_allowed(telegram_id):
        await message.answer(f"Чат {telegram_id} уже в списке.")
        await state.clear()
        return

    # Save resolved data, ask for description
    await state.update_data(telegram_id=telegram_id, username=username)
    await state.set_state(AddChat.waiting_for_description)
    await message.answer("Введите описание для этого чата (например, название группы):")


@router.message(AddChat.waiting_for_description)
async def on_chat_add_description(
    message: Message, state: FSMContext, repo: Repository
) -> None:
    description = (message.text or "").strip()
    if not description:
        await message.answer("Введите описание.")
        return

    data = await state.get_data()
    telegram_id = data["telegram_id"]
    username = data.get("username")

    await repo.add_allowed_chat(telegram_id, username=username, description=description)
    await state.clear()

    await message.answer(f"✅ Чат добавлен: {description}")
    await _show_chats_list(message, repo)


@router.callback_query(F.data.startswith("chats:remove:"))
async def on_chat_remove(
    callback: CallbackQuery, repo: Repository
) -> None:
    db_id = int(callback.data.split(":")[2])

    # Find the chat to get its telegram_id
    from db.models import AllowedChat
    chat = await repo.session.get(AllowedChat, db_id)
    if chat is None:
        await callback.answer("Чат не найден.", show_alert=True)
        return

    display = f"@{chat.username}" if chat.username else str(chat.telegram_id)
    await repo.remove_allowed_chat(chat.telegram_id)
    await callback.answer(f"Чат {display} удалён.")
    await _show_chats_list(callback.message, repo)
