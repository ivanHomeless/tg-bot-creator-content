import json
import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from apscheduler.triggers.cron import CronTrigger

from bot.keyboards.inline import settings_keyboard
from bot.keyboards.reply import BTN_SETTINGS
from bot.states.fsm import EditPrompt, EditProviders, EditSchedule
from db.repo import Repository

logger = logging.getLogger(__name__)

router = Router()

DONE_PROMPT_CB = "prompt:done"


def _done_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Я закончил отправку", callback_data=DONE_PROMPT_CB)]
        ]
    )


# ---- entry ----

@router.message(F.text == BTN_SETTINGS)
async def cmd_settings(message: Message) -> None:
    await message.answer("⚙️ Настройки", reply_markup=settings_keyboard())


# ========== PROMPT ==========

@router.callback_query(F.data == "settings:prompt")
async def on_edit_prompt_start(
    callback: CallbackQuery, state: FSMContext, repo: Repository
) -> None:
    current = await repo.get_setting("system_prompt")
    if current:
        await callback.message.answer(
            f"Текущий промпт:\n\n<pre>{current}</pre>",
            parse_mode="HTML",
        )
    await state.set_state(EditPrompt.collecting_parts)
    await state.update_data(prompt_parts=[])
    await callback.message.answer(
        "Отправьте новый промпт. Можно несколькими сообщениями и/или .txt файлами.\n"
        "Когда закончите, нажмите кнопку ниже.",
        reply_markup=_done_keyboard(),
    )
    await callback.answer()


@router.message(EditPrompt.collecting_parts, F.document)
async def on_prompt_document(
    message: Message, state: FSMContext, bot: Bot
) -> None:
    doc = message.document
    if not doc.file_name.endswith(".txt"):
        await message.answer("Поддерживаются только .txt файлы.")
        return

    file = await bot.download(doc)
    text = file.read().decode("utf-8", errors="replace")
    data = await state.get_data()
    parts = data.get("prompt_parts", [])
    parts.append(text)
    await state.update_data(prompt_parts=parts)
    await message.answer("📄 Файл принят. Продолжайте или нажмите «Я закончил».")


@router.message(EditPrompt.collecting_parts, F.text)
async def on_prompt_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    parts = data.get("prompt_parts", [])
    parts.append(message.text)
    await state.update_data(prompt_parts=parts)
    await message.answer("✏️ Принято. Продолжайте или нажмите «Я закончил».")


@router.callback_query(F.data == DONE_PROMPT_CB)
async def on_prompt_done(
    callback: CallbackQuery, state: FSMContext, repo: Repository
) -> None:
    data = await state.get_data()
    parts = data.get("prompt_parts", [])
    if not parts:
        await callback.answer("Вы ничего не отправили.")
        return

    full_prompt = "\n".join(parts)
    await repo.set_setting("system_prompt", full_prompt)
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("✅ Промпт обновлён.")
    await callback.answer()


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
    message: Message, state: FSMContext, repo: Repository
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
    await state.clear()
    await message.answer(f"✅ Расписание обновлено: <code>{cron_expr}</code>", parse_mode="HTML")


# ========== PROVIDERS ==========

@router.callback_query(F.data == "settings:providers")
async def on_edit_providers_start(
    callback: CallbackQuery, state: FSMContext, repo: Repository
) -> None:
    current = await repo.get_setting("llm_providers")
    if current:
        await callback.message.answer(
            f"Текущий конфиг провайдеров:\n\n<pre>{current}</pre>",
            parse_mode="HTML",
        )
    else:
        await callback.message.answer("Конфиг провайдеров пока не задан.")

    await callback.message.answer(
        "Отправьте .json файл с новым конфигом провайдеров."
    )
    await state.set_state(EditProviders.waiting_for_json)
    await callback.answer()


@router.message(EditProviders.waiting_for_json, F.document)
async def on_providers_json_file(
    message: Message, state: FSMContext, repo: Repository, bot: Bot
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

    await repo.set_setting("llm_providers", json.dumps(data, ensure_ascii=False))
    await state.clear()
    await message.answer(f"✅ Конфиг провайдеров обновлён ({len(data)} шт.).")


@router.message(EditProviders.waiting_for_json)
async def on_providers_not_a_file(message: Message) -> None:
    await message.answer("Отправьте .json файл с конфигом провайдеров.")
