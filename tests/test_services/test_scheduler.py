import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from apscheduler.triggers.cron import CronTrigger

from db.models import PostStatus
from services.scheduler import publish_job, reschedule, JOB_ID


def _make_post(post_id: int, status: str = "approved"):
    post = MagicMock()
    post.id = post_id
    post.status = status
    post.generated_text = "Post text"
    post.media_ids = None
    post.published_at = None
    return post


def _make_session_factory(repo_mock):
    """Create a mock session_factory that yields a session with repo."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock()
    factory.return_value = session
    return factory, session


class TestScheduler:
    @patch("services.scheduler.publish_post")
    @patch("services.scheduler.Repository")
    async def test_publish_job_publishes_oldest(self, mock_repo_cls, mock_publish):
        """Job publishes the oldest approved post."""
        post = _make_post(1)
        repo_instance = AsyncMock()
        repo_instance.get_oldest_approved_post.return_value = post
        mock_repo_cls.return_value = repo_instance

        factory, session = _make_session_factory(repo_instance)
        bot = AsyncMock()

        await publish_job(factory, bot, -100)

        mock_publish.assert_called_once_with(bot, post, -100)
        repo_instance.update_post_status.assert_called_once_with(1, PostStatus.published)

    @patch("services.scheduler.publish_post")
    @patch("services.scheduler.Repository")
    async def test_publish_job_empty_queue_no_error(self, mock_repo_cls, mock_publish):
        """Empty queue → silent skip, no publish call."""
        repo_instance = AsyncMock()
        repo_instance.get_oldest_approved_post.return_value = None
        mock_repo_cls.return_value = repo_instance

        factory, session = _make_session_factory(repo_instance)
        bot = AsyncMock()

        await publish_job(factory, bot, -100)

        mock_publish.assert_not_called()

    @patch("services.scheduler.publish_post")
    @patch("services.scheduler.Repository")
    async def test_publish_job_skips_editing(self, mock_repo_cls, mock_publish):
        """get_oldest_approved_post only returns approved, so editing posts are skipped."""
        # The repo method filters by approved status, so it won't return editing posts.
        # If queue has only editing posts, get_oldest_approved_post returns None.
        repo_instance = AsyncMock()
        repo_instance.get_oldest_approved_post.return_value = None
        mock_repo_cls.return_value = repo_instance

        factory, session = _make_session_factory(repo_instance)
        bot = AsyncMock()

        await publish_job(factory, bot, -100)

        mock_publish.assert_not_called()

    def test_reschedule_updates_trigger(self):
        """reschedule calls scheduler.reschedule_job with new CronTrigger."""
        scheduler = MagicMock()

        reschedule(scheduler, "30 18 * * *")

        scheduler.reschedule_job.assert_called_once()
        call_args = scheduler.reschedule_job.call_args
        assert call_args[0][0] == JOB_ID
        trigger = call_args[1]["trigger"]
        assert isinstance(trigger, CronTrigger)

    def test_cron_trigger_validation(self):
        """Valid cron passes, invalid raises ValueError."""
        # Valid
        trigger = CronTrigger.from_crontab("0 9 * * *")
        assert trigger is not None

        # Invalid
        with pytest.raises(ValueError):
            CronTrigger.from_crontab("invalid cron expression")
