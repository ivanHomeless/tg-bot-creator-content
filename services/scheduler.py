import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import async_sessionmaker

from aiogram import Bot

from db.models import PostStatus
from db.repo import Repository
from services.publisher import publish_post

logger = logging.getLogger(__name__)

JOB_ID = "auto_publish"


async def publish_job(
    session_factory: async_sessionmaker,
    bot: Bot,
    channel_id: int,
) -> None:
    """Publish the oldest approved post. Silent skip if queue is empty."""
    async with session_factory() as session:
        repo = Repository(session)
        post = await repo.get_oldest_approved_post()

        if post is None:
            logger.debug("Auto-publish: queue empty, skipping")
            return

        try:
            await publish_post(bot, post, channel_id)
            await repo.update_post_status(post.id, PostStatus.published)
            post.published_at = datetime.now(timezone.utc)
            await session.commit()
            logger.info("Auto-published post #%d", post.id)
        except Exception as e:
            logger.error("Auto-publish failed for post #%d: %s", post.id, e)


def create_scheduler(
    session_factory: async_sessionmaker,
    bot: Bot,
    channel_id: int,
    cron_expr: str,
) -> AsyncIOScheduler:
    """Create and configure the scheduler with the auto-publish job."""
    scheduler = AsyncIOScheduler()
    trigger = CronTrigger.from_crontab(cron_expr)

    scheduler.add_job(
        publish_job,
        trigger=trigger,
        id=JOB_ID,
        replace_existing=True,
        kwargs={
            "session_factory": session_factory,
            "bot": bot,
            "channel_id": channel_id,
        },
    )

    return scheduler


def reschedule(scheduler: AsyncIOScheduler, new_cron: str) -> None:
    """Update the auto-publish job trigger."""
    trigger = CronTrigger.from_crontab(new_cron)
    scheduler.reschedule_job(JOB_ID, trigger=trigger)
    logger.info("Rescheduled auto-publish to: %s", new_cron)
