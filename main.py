import asyncio
import json
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import create_post, post_actions, queue, settings, start
from bot.middlewares.access import AllowedChatsMiddleware
from bot.middlewares.media_group import MediaGroupMiddleware
from config.settings import get_settings
from db.engine import build_engine, build_session_factory
from db.repo import Repository
from services.ai.prompts import DEFAULT_SYSTEM_PROMPT
from services.publisher import publish_post
from services.scheduler import create_scheduler

logger = logging.getLogger(__name__)


async def _seed_defaults(session_factory) -> None:
    """Seed default settings if not yet present."""
    async with session_factory() as session:
        repo = Repository(session)
        if await repo.get_setting("system_prompt") is None:
            await repo.set_setting("system_prompt", DEFAULT_SYSTEM_PROMPT)
        if await repo.get_setting("cron_schedule") is None:
            await repo.set_setting("cron_schedule", "0 9 * * *")
        if await repo.get_setting("llm_providers") is None:
            await repo.set_setting("llm_providers", "[]")


def _build_llm_router(providers_json: str):
    """Build ProviderRouter from JSON config string."""
    from services.llm.router import ProviderRouter

    try:
        config = json.loads(providers_json)
    except (json.JSONDecodeError, TypeError):
        config = []
    if not config:
        return None
    return ProviderRouter.from_config(config)


async def build_app(cfg=None):
    """Build and configure all application components. Returns (dp, bot, scheduler, engine).

    Separated from main() for testability.
    """
    if cfg is None:
        cfg = get_settings()

    engine = build_engine(cfg.database_url)
    session_factory = build_session_factory(engine)

    # Seed defaults
    await _seed_defaults(session_factory)

    # Load settings from DB
    async with session_factory() as session:
        repo = Repository(session)
        cron = await repo.get_setting("cron_schedule") or cfg.default_cron
        providers_json = await repo.get_setting("llm_providers") or "[]"

    llm_router = _build_llm_router(providers_json)

    bot = Bot(
        token=cfg.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Session middleware — injects repo into every handler
    from aiogram import BaseMiddleware
    from typing import Any, Awaitable, Callable, Dict
    from aiogram.types import TelegramObject

    class SessionMiddleware(BaseMiddleware):
        async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any],
        ) -> Any:
            async with session_factory() as session:
                data["repo"] = Repository(session)
                return await handler(event, data)

    session_mw = SessionMiddleware()
    dp.message.middleware(session_mw)
    dp.callback_query.middleware(session_mw)

    # Access control + media group
    access_mw = AllowedChatsMiddleware()
    dp.message.middleware(access_mw)
    dp.callback_query.middleware(access_mw)
    dp.message.middleware(MediaGroupMiddleware())

    # Routers
    dp.include_router(start.router)
    dp.include_router(create_post.router)
    dp.include_router(post_actions.router)
    dp.include_router(queue.router)
    dp.include_router(settings.router)

    # DI data available in all handlers via **kwargs
    dp["tavily_api_key"] = cfg.tavily_api_key
    dp["llm_router"] = llm_router
    dp["channel_id"] = cfg.channel_id
    dp["session_factory"] = session_factory

    # Closure so handlers call publish_post(post) without bot/channel_id
    async def _publish_post(post):
        await publish_post(bot, post, cfg.channel_id)

    dp["publish_post"] = _publish_post

    # Scheduler
    scheduler = create_scheduler(session_factory, bot, cfg.channel_id, cron)
    dp["scheduler"] = scheduler

    return dp, bot, scheduler, engine


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    dp, bot, scheduler, engine = await build_app()

    logger.info("Starting bot...")
    scheduler.start()
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
